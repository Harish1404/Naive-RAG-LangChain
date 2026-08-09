"""
Conversation management — the endpoints behind a Claude-style chat sidebar:
start a new chat, list past chats, open one, rename it, delete it.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.ids import is_conversation_id
from app.memory.store import conversation_store
from app.schemas.chat import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    RenameRequest,
    conversation_detail,
    conversation_out,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


async def _require_conversation(conversation_id: str, user_id: Optional[str] = None) -> dict:
    """
    Loads a conversation or raises the right error.

    The id is shape-checked first so junk gets a 422 rather than a 404 — the
    difference between "you typed it wrong" and "it isn't there" is worth
    keeping.
    """
    if not is_conversation_id(conversation_id):
        raise HTTPException(status_code=422, detail="Malformed conversation_id")

    conversation = await conversation_store.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationCreate | None = None):
    """New chat. Returns the id to send with the next /chatbot call."""
    body = body or ConversationCreate()
    conversation = await conversation_store.create_conversation(body.user_id, body.title)
    return conversation_out(conversation)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user_id: str = "default_user",
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    """The sidebar: most recently active thread first."""
    docs = await conversation_store.list_conversations(user_id, limit=limit, skip=skip)
    return [conversation_out(doc) for doc in docs]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    before_seq: Optional[int] = Query(default=None, ge=0),
):
    """
    The full thread, oldest message first.

    Paginated backwards with `before_seq` — pass the lowest `seq` you already
    have to page further up a long conversation.
    """
    conversation = await _require_conversation(conversation_id)
    messages = await conversation_store.get_transcript(
        conversation_id, limit=limit, before_seq=before_seq
    )
    return conversation_detail(conversation, messages)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: str, body: RenameRequest):
    await _require_conversation(conversation_id)

    updated = await conversation_store.rename_conversation(conversation_id, body.title)
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversation_out(updated)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """
    Soft delete: the thread disappears from the sidebar and can no longer be
    posted to, but its messages stay on disk and remain recoverable.
    """
    await _require_conversation(conversation_id)
    await conversation_store.delete_conversation(conversation_id)
    return None
