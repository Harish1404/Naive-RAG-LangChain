"""
The `connectors` collection: one document per (user, provider) link.

Mongo only, no policy and no crypto — the service layer decides whether a
connection may be made and hands this the already-encrypted token. That split
is why nothing here imports app/core/crypto.py.

The stored token is encrypted, not hashed, and the distinction is the whole
reason this collection needs care: unlike `refresh_tokens`, a leak here plus a
leak of CONNECTOR_ENC_KEY yields working GitHub credentials. So the plaintext
token never appears in a document, a log line, or a return value that is not
explicitly asked for — see `get_token_ciphertext`.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from pymongo import ReturnDocument

from app.core.ids import new_connector_id
from app.db.mongodb import get_connector_collection

logger = logging.getLogger(__name__)

STATUS_CONNECTED = "connected"
STATUS_ERROR = "error"

# Never returned to a route, never logged. Applied as a projection so the
# ciphertext cannot leak into an API response by someone forgetting to strip it.
_PUBLIC_PROJECTION = {"token_ciphertext": 0}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorRepository:
    @property
    def collection(self):
        # Resolved per call, not in __init__: the Motor client does not exist
        # until connect_to_mongo() runs, and this module is imported before it.
        return get_connector_collection()

    async def upsert(
        self,
        user_id: str,
        provider: str,
        token_ciphertext: str,
        key_version: int,
        scopes: list[str],
        account_login: str = "",
        account_avatar_url: str = "",
    ) -> dict:
        """
        Records a successful connection, replacing any previous one.

        Upsert rather than insert because reconnecting is normal — a user who
        re-consents to widen scopes must end up with one document holding the
        new token, not two documents racing to be found first. The unique
        (user_id, provider) index is what makes this safe under a double click.
        """
        now = _now()
        doc = await self.collection.find_one_and_update(
            {"user_id": user_id, "provider": provider},
            {
                "$set": {
                    "status": STATUS_CONNECTED,
                    "token_ciphertext": token_ciphertext,
                    "key_version": key_version,
                    "scopes": scopes,
                    "account_login": account_login,
                    "account_avatar_url": account_avatar_url,
                    "updated_at": now,
                    "last_error": None,
                },
                "$setOnInsert": {
                    "_id": new_connector_id(),
                    "user_id": user_id,
                    "provider": provider,
                    "connected_at": now,
                    "last_used_at": None,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
            projection=_PUBLIC_PROJECTION,
        )
        logger.info(f"Connector {provider!r} connected for {user_id}")
        return doc

    async def get(self, user_id: str, provider: str) -> Optional[dict]:
        """The connection without its token. None if there is not one."""
        return await self.collection.find_one(
            {"user_id": user_id, "provider": provider},
            _PUBLIC_PROJECTION,
        )

    async def list_for_user(self, user_id: str) -> list[dict]:
        """Every connection this user has, tokens excluded."""
        cursor = self.collection.find({"user_id": user_id}, _PUBLIC_PROJECTION)
        return await cursor.to_list(length=50)

    async def get_token_ciphertext(self, user_id: str, provider: str) -> Optional[str]:
        """
        The encrypted token, for the one caller that needs to decrypt it.

        Deliberately a separate method rather than a flag on `get`. Reading a
        credential should be an explicit act that is easy to grep for, not
        something a route can do by forgetting to pass `include_token=False`.
        """
        doc = await self.collection.find_one(
            {"user_id": user_id, "provider": provider},
            {"token_ciphertext": 1},
        )
        return (doc or {}).get("token_ciphertext")

    async def mark_used(self, user_id: str, provider: str) -> None:
        """Best-effort telemetry: when this connection last did real work."""
        await self.collection.update_one(
            {"user_id": user_id, "provider": provider},
            {"$set": {"last_used_at": _now()}},
        )

    async def mark_error(self, user_id: str, provider: str, message: str) -> None:
        """
        Records that the connection stopped working, without deleting it.

        Kept rather than removed so the UI can say "reconnect GitHub, the token
        was revoked" instead of silently showing a Connect button and leaving
        the user wondering where their connection went.
        """
        await self.collection.update_one(
            {"user_id": user_id, "provider": provider},
            {
                "$set": {
                    "status": STATUS_ERROR,
                    "last_error": message[:300],
                    "updated_at": _now(),
                }
            },
        )

    async def delete(self, user_id: str, provider: str) -> bool:
        """
        Hard delete. True if there was something to remove.

        Not a soft delete, unlike conversations: keeping a revoked credential
        around has no upside and every extra copy is another thing to leak.
        """
        result = await self.collection.delete_one(
            {"user_id": user_id, "provider": provider}
        )
        if result.deleted_count:
            logger.info(f"Connector {provider!r} disconnected for {user_id}")
        return result.deleted_count > 0


# One shared instance, same pattern as the other repositories.
connector_repo = ConnectorRepository()
