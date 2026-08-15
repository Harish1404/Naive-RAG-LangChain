"""
The `users` collection: who someone is to Clerk, and whether they may act here.

Kept deliberately small. Anything a user can edit about themselves lives in
`profiles` instead (see profile_repo), so this collection only ever changes as
a result of an authorization decision — sign-in, ban, verification, revocation.
"""

import logging
from datetime import datetime, timezone

from pymongo import ReturnDocument

from app.core.ids import new_user_id
from app.db.mongodb import get_user_collection

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserRepository:
    """Mongo access for user documents. No policy — see app/services/auth_service.py."""

    async def get_by_id(self, user_id: str) -> dict | None:
        return await get_user_collection().find_one({"_id": user_id})

    async def get_by_clerk_id(self, clerk_user_id: str) -> dict | None:
        return await get_user_collection().find_one({"clerk_user_id": clerk_user_id})

    async def upsert_from_clerk(
        self,
        clerk_user_id: str,
        email: str,
        email_verified: bool = False,
    ) -> dict:
        """
        Finds or creates the user behind a Clerk identity, in one round trip.

        This is an upsert rather than a get-then-insert because first sign-in is
        exactly when a race is possible: a page that fires two requests at once
        would otherwise run two inserts and hit the unique index on the second.
        `$setOnInsert` carries the fields that must never be reset on a returning
        user — most importantly is_banned, which a re-login must not clear.
        """
        now = _now()

        return await get_user_collection().find_one_and_update(
            {"clerk_user_id": clerk_user_id},
            {
                "$set": {
                    "email": email,
                    "email_verified": email_verified,
                    "updated_at": now,
                    "last_login_at": now,
                },
                "$setOnInsert": {
                    "_id": new_user_id(),
                    "clerk_user_id": clerk_user_id,
                    # Distinct from email_verified: that is Clerk's fact about the
                    # address, this is the app's own gate, so it can be revoked
                    # without touching the provider.
                    "is_verified": True,
                    "is_banned": False,
                    "ban_reason": None,
                    "banned_at": None,
                    "role": "user",
                    # Bumped to invalidate every access token already issued.
                    "token_version": 0,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def set_banned(
        self, user_id: str, banned: bool, reason: str | None = None
    ) -> dict | None:
        """
        Bans or unbans, and bumps token_version on the way in.

        The bump is the part that matters: access tokens are verified without a
        database read, so without invalidating them a banned user would keep
        working until their current token expired.
        """
        update: dict = {
            "$set": {
                "is_banned": banned,
                "ban_reason": reason if banned else None,
                "banned_at": _now() if banned else None,
                "updated_at": _now(),
            }
        }
        if banned:
            update["$inc"] = {"token_version": 1}

        return await get_user_collection().find_one_and_update(
            {"_id": user_id}, update, return_document=ReturnDocument.AFTER
        )

    async def set_verified(self, user_id: str, verified: bool) -> dict | None:
        return await get_user_collection().find_one_and_update(
            {"_id": user_id},
            {"$set": {"is_verified": verified, "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def sync_email(
        self, clerk_user_id: str, email: str, email_verified: bool
    ) -> dict | None:
        """Applies a `user.updated` webhook. No-op if we have never seen them."""
        return await get_user_collection().find_one_and_update(
            {"clerk_user_id": clerk_user_id},
            {
                "$set": {
                    "email": email,
                    "email_verified": email_verified,
                    "updated_at": _now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def bump_token_version(self, user_id: str) -> dict | None:
        """Invalidates every access token outstanding for this user."""
        return await get_user_collection().find_one_and_update(
            {"_id": user_id},
            {"$inc": {"token_version": 1}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )


user_repo = UserRepository()
