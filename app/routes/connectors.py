"""
Connectors — linking a third-party account so its MCP tools become available.

Four endpoints, and one of them is unlike anything else in this app:

    GET    /connectors                      what this user has connected
    GET    /connectors/github/authorize     -> { authorize_url }, the frontend navigates
    GET    /connectors/github/callback      GitHub sends the BROWSER here
    DELETE /connectors/github               revoke and forget

The callback is the odd one. It is not called by our frontend, it is a
navigation performed by GitHub's redirect, so it cannot be authenticated by our
session cookie and cannot usefully return JSON. Identity comes from the signed
`state` instead, and every outcome — success and failure alike — ends as a 302
back to the frontend with a query flag for the toast.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import get_current_user_id
from app.core.config import settings
from app.core.security import TokenError, decode_oauth_state
from app.schemas.connectors import AuthorizeOut, ConnectorOut, connector_out
from app.services.connector_service import GITHUB, ConnectorError, connector_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["Connectors"])

# The catalogue the frontend renders. Only GitHub is wired up; the rest are
# listed so the page has something to show and so adding one later is a line
# here plus a provider module, not a redesign.
CATALOGUE: list[tuple[str, str, bool]] = [
    ("github", "GitHub", True),
    ("gmail", "Gmail", False),
    ("slack", "Slack", False),
    ("notion", "Notion", False),
    ("google_drive", "Google Drive", False),
    ("postgres", "PostgreSQL", False),
    ("web_search", "Web Search", False),
    ("google_calendar", "Google Calendar", False),
    ("confluence", "Confluence", False),
]


def _frontend_redirect(**params: str) -> RedirectResponse:
    """Back to the connectors page with a flag for the toast."""
    base = (settings.FRONTEND_URL or "http://localhost:3000").rstrip("/")
    query = "&".join(f"{k}={v}" for k, v in params.items())
    # 303 rather than 302: the browser must switch to GET regardless of how it
    # arrived, which is exactly what "see this other resource instead" means.
    return RedirectResponse(f"{base}/connectors?{query}", status_code=303)


@router.get("", response_model=list[ConnectorOut])
async def list_connectors(user_id: str = Depends(get_current_user_id)):
    """Every provider the page can show, with this user's status on each."""
    connected = {
        doc["provider"]: doc
        for doc in await connector_service.list_for_user(user_id)
    }

    return [
        connector_out(provider, label, connected.get(provider), supported=supported)
        for provider, label, supported in CATALOGUE
    ]


@router.get("/github/authorize", response_model=AuthorizeOut)
async def github_authorize(user_id: str = Depends(get_current_user_id)):
    """
    The URL that starts GitHub consent, with a signed state tying it to caller.

    Deliberately not a redirect — see the module docstring and
    ConnectorService.authorize_url.
    """
    try:
        return AuthorizeOut(authorize_url=connector_service.authorize_url(user_id))
    except ConnectorError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e


@router.get("/github/callback", include_in_schema=False)
async def github_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    """
    Where GitHub sends the browser after the user accepts or declines.

    Unauthenticated by design: this is a cross-site navigation and the session
    cookie may not ride along. The signed `state` is what proves who this is,
    and it is verified before anything else happens.

    Never raises. A user who lands here after declining consent gets a toast,
    not a stack trace.
    """
    # The user pressed Cancel, or GitHub refused outright.
    if error:
        logger.info(f"GitHub consent declined or failed: {error}")
        return _frontend_redirect(error=error_description or error)

    if not code or not state:
        return _frontend_redirect(error="Incomplete response from GitHub")

    try:
        user_id = decode_oauth_state(state, GITHUB)
    except TokenError as e:
        # Forged, expired, or replayed from another provider's flow.
        logger.warning(f"Rejected GitHub callback state: {e}")
        return _frontend_redirect(error=str(e))

    try:
        await connector_service.complete(user_id, code)
    except ConnectorError as e:
        logger.error(f"GitHub connection failed for {user_id}: {e.message}")
        return _frontend_redirect(error=e.message)
    except Exception:
        logger.exception(f"Unexpected error completing GitHub connection for {user_id}")
        return _frontend_redirect(error="Could not complete the connection")

    return _frontend_redirect(connected=GITHUB)


@router.delete("/github", status_code=status.HTTP_204_NO_CONTENT)
async def github_disconnect(user_id: str = Depends(get_current_user_id)):
    """
    Revoke the GitHub token and forget the connection.

    204 whether or not there was one to remove — disconnecting something already
    disconnected is not an error, and answering 404 would only tell the caller
    something they cannot act on.
    """
    await connector_service.disconnect(user_id)
    return None
