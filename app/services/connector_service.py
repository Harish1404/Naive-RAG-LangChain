"""
Connecting and disconnecting a third-party provider.

Policy lives here; `app/repositories/connector_repo.py` does the Mongo work and
`app/core/crypto.py` does the encryption. This module is the only place that
holds a provider access token in plaintext, and it holds it for exactly as long
as it takes to encrypt it.

The flow, end to end:

    1. The user clicks Connect. authorize_url() mints a signed state and returns
       a github.com URL — it does NOT redirect, see the note there.
    2. GitHub sends the browser back to /connectors/github/callback with a code.
    3. complete() swaps the code for a token, reads the account it belongs to,
       encrypts the token and stores it.
    4. disconnect() revokes the token at GitHub before forgetting it.
"""

import logging
from urllib.parse import urlencode

import httpx

from app.core import crypto
from app.core.config import settings
from app.core.security import create_oauth_state
from app.repositories.connector_repo import connector_repo

logger = logging.getLogger(__name__)

GITHUB = "github"

_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_URL = "https://api.github.com/user"
_REVOKE_URL = "https://api.github.com/applications/{client_id}/token"

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class ConnectorError(Exception):
    """A connection attempt failed for a reason worth showing the user."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ConnectorService:
    # ── Connect ──────────────────────────────────────────────────────────────

    def authorize_url(self, user_id: str) -> str:
        """
        Where the browser should be sent to start the GitHub consent flow.

        Returned as a string for the caller to hand the frontend, rather than
        issued as a 302: the frontend calls this over XHR with credentials, and
        a redirect to github.com would be followed by the XHR layer and die on
        CORS. The browser has to navigate itself.
        """
        if not settings.github_connector_configured:
            raise ConnectorError(
                "GitHub connector is not configured on this server", status_code=503
            )

        params = {
            "client_id": settings.github_client_id,
            "redirect_uri": settings.github_redirect_uri,
            "scope": settings.github_oauth_scopes,
            "state": create_oauth_state(user_id, GITHUB),
            # Force the consent screen even when a grant already exists, so
            # reconnecting to widen scopes actually asks rather than silently
            # handing back the old, narrower token.
            "allow_signup": "false",
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def complete(self, user_id: str, code: str) -> dict:
        """
        Exchange the callback code for a token, then store it encrypted.

        Everything that can fail here fails as a ConnectorError carrying a
        message fit to put in a redirect query string — the caller is a browser
        navigation, not an API client.
        """
        token, scopes = await self._exchange_code(code)
        account = await self._read_account(token)

        # The plaintext token stops existing here. Nothing below this line, and
        # nothing in the repository, ever sees it.
        ciphertext = crypto.encrypt(token)

        doc = await connector_repo.upsert(
            user_id=user_id,
            provider=GITHUB,
            token_ciphertext=ciphertext,
            key_version=crypto.KEY_VERSION,
            scopes=scopes,
            account_login=account.get("login", ""),
            account_avatar_url=account.get("avatar_url", ""),
        )

        # A previous connection's tools may still be cached for this user, and
        # they were built with the old token. Imported here rather than at
        # module level to keep the AI layer out of this module's import graph.
        from app.ai.mcp.client import invalidate

        invalidate(user_id)

        return doc

    async def _exchange_code(self, code: str) -> tuple[str, list[str]]:
        """POST the code to GitHub, get an access token and the granted scopes."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                response = await client.post(
                    _TOKEN_URL,
                    data={
                        "client_id": settings.github_client_id,
                        "client_secret": settings.github_client_secret,
                        "code": code,
                        "redirect_uri": settings.github_redirect_uri,
                    },
                    # Without this GitHub answers form-encoded, which is easy to
                    # misparse into a token that looks fine and is not.
                    headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as e:
                logger.error(f"GitHub token exchange failed to send: {e}")
                raise ConnectorError("Could not reach GitHub", status_code=502) from e

        if response.status_code != 200:
            logger.error(f"GitHub token exchange returned {response.status_code}")
            raise ConnectorError("GitHub rejected the authorization", status_code=502)

        payload = response.json()

        # GitHub reports failures as HTTP 200 with an `error` key, so the status
        # code alone is not enough to know this worked.
        if payload.get("error"):
            logger.error(f"GitHub token exchange error: {payload.get('error')}")
            raise ConnectorError(
                payload.get("error_description") or "GitHub refused the request"
            )

        token = payload.get("access_token")
        if not token:
            raise ConnectorError("GitHub returned no access token", status_code=502)

        # Space-separated in the response; stored as a list so the UI can show
        # what was actually granted, which may be narrower than what we asked.
        scopes = [s for s in (payload.get("scope") or "").split(",") if s]
        return token, scopes

    async def _read_account(self, token: str) -> dict:
        """Which GitHub account the token belongs to, for display on the card."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            try:
                response = await client.get(
                    _USER_URL,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
            except httpx.HTTPError as e:
                logger.warning(f"Could not read GitHub account: {e}")
                return {}

        if response.status_code != 200:
            # Not fatal — the token works even if we cannot label the card.
            logger.warning(f"GitHub /user returned {response.status_code}")
            return {}

        return response.json()

    # ── Read ─────────────────────────────────────────────────────────────────

    async def status(self, user_id: str) -> dict | None:
        """This user's GitHub connection, without its token. None if absent."""
        return await connector_repo.get(user_id, GITHUB)

    async def list_for_user(self, user_id: str) -> list[dict]:
        """Every connection this user has, tokens excluded."""
        return await connector_repo.list_for_user(user_id)

    # ── Disconnect ───────────────────────────────────────────────────────────

    async def disconnect(self, user_id: str) -> bool:
        """
        Revoke the token at GitHub, then forget it. True if there was one.

        Revocation is attempted first and its failure is tolerated. The ordering
        matters: deleting our row without revoking would leave a live grant on
        the user's GitHub account that neither they nor we can see any more. If
        revocation fails we still delete, because a user who clicked Disconnect
        must not be left connected — they can finish the job from GitHub's
        applications page.
        """
        ciphertext = await connector_repo.get_token_ciphertext(user_id, GITHUB)

        if ciphertext:
            try:
                await self._revoke(crypto.decrypt(ciphertext))
            except crypto.CryptoError as e:
                # Key rotated or row corrupted — nothing to revoke with.
                logger.warning(f"Could not decrypt token to revoke it: {e}")
            except Exception as e:
                logger.warning(f"GitHub token revocation failed: {e}")

        deleted = await connector_repo.delete(user_id, GITHUB)

        from app.ai.mcp.client import invalidate

        invalidate(user_id)

        return deleted

    async def _revoke(self, token: str) -> None:
        """
        Ask GitHub to invalidate the token.

        Authenticated with the OAuth app's own client id and secret via HTTP
        Basic, not with the token itself — this is the app saying "forget this
        grant", which is not something the token may do on its own behalf.
        """
        url = _REVOKE_URL.format(client_id=settings.github_client_id)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.request(
                "DELETE",
                url,
                auth=(settings.github_client_id, settings.github_client_secret),
                json={"access_token": token},
                headers={"Accept": "application/vnd.github+json"},
            )

        # 204 is success. 404 means it was already gone, which is the same
        # outcome from the user's point of view.
        if response.status_code not in (204, 404):
            logger.warning(f"GitHub revocation returned {response.status_code}")


connector_service = ConnectorService()
