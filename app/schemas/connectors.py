"""
Request and response models for the connectors endpoints.

Same rule as app/schemas/chat.py: the document shape stays inside the backend.
And one rule specific to this file — **no model here has a token field**. The
stored credential is encrypted and has no business crossing the API boundary in
any form, so there is deliberately nowhere for it to go.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

# What the frontend renders. `available` means we support it and the user has
# not connected it; `coming_soon` is every provider we have not built yet.
ConnectorStatus = Literal["available", "connected", "error", "coming_soon"]


class ConnectorOut(BaseModel):
    provider: str
    label: str
    status: ConnectorStatus
    # Populated only when connected — which account, so the card can show it.
    account_login: Optional[str] = None
    account_avatar_url: Optional[str] = None
    scopes: list[str] = []
    connected_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    # Set when status is "error", e.g. the token was revoked from GitHub's side.
    last_error: Optional[str] = None


class AuthorizeOut(BaseModel):
    """
    Where the browser should navigate to begin consent.

    Returned as a URL instead of a 302 because the caller is an XHR that would
    follow the redirect itself and fail CORS — see ConnectorService.authorize_url.
    """

    authorize_url: str


def connector_out(
    provider: str,
    label: str,
    doc: Optional[dict],
    supported: bool = True,
) -> ConnectorOut:
    """Maps a stored document (or its absence) to what the card needs."""
    if not supported:
        return ConnectorOut(provider=provider, label=label, status="coming_soon")

    if doc is None:
        return ConnectorOut(provider=provider, label=label, status="available")

    return ConnectorOut(
        provider=provider,
        label=label,
        status=doc.get("status", "connected"),
        account_login=doc.get("account_login") or None,
        account_avatar_url=doc.get("account_avatar_url") or None,
        scopes=doc.get("scopes") or [],
        connected_at=doc.get("connected_at"),
        last_used_at=doc.get("last_used_at"),
        last_error=doc.get("last_error"),
    )
