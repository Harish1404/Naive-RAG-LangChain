"""
Writing a finished answer back to MongoDB.

This is the AI layer's one deliberate touchpoint with storage — see the note in
app/ai/__init__.py. It is isolated here so the nodes, the router and the tool
loop stay pure: they produce tokens and know nothing about where those tokens
end up.

The two entry points differ only in *when* they are safe to call, and that
difference is the whole reason both exist. Read schedule_persist before changing
either.
"""

import asyncio
import logging

from app.ai.chat.context import TurnContext
from app.memory.store import conversation_store

logger = logging.getLogger(__name__)

# Strong references to detached history writes. asyncio only keeps a weak
# reference to a running task, so without this a fire-and-forget write can be
# garbage collected mid-flight and silently never happen.
_pending_writes: set[asyncio.Task] = set()


def schedule_persist(ctx: TurnContext, answer: str) -> None:
    """
    Saves a cut-off answer from outside the answering generator's teardown.

    Synchronous on purpose — it only schedules the write. See the note in
    ChatService.chat()'s finally for why awaiting from a finalizing generator
    does not work: aclose() has already returned by then and the await is
    cancelled.
    """
    if not answer.strip():
        return

    try:
        task = asyncio.create_task(persist_answer(ctx, answer, completed=False))
    except RuntimeError as e:
        # No running loop — the app is shutting down. Nothing to be done.
        logger.warning(
            f"Could not schedule partial answer for {ctx.conversation_id}: {e}"
        )
        return

    _pending_writes.add(task)
    task.add_done_callback(_pending_writes.discard)


async def persist_answer(ctx: TurnContext, answer: str, completed: bool) -> None:
    """
    Writes the finished answer to MongoDB so the next turn can see it.

    Two deliberate choices here. Nothing is stored for an empty answer,
    which keeps a failed turn's error text out of the replayed history.
    And a write failure is logged, never raised — the user already has
    their answer on screen by this point, and turning a storage hiccup
    into a broken response would be a worse trade.
    """
    if not answer.strip():
        return

    try:
        await conversation_store.append_message(
            ctx.conversation_id,
            role="assistant",
            content=answer,
            route=ctx.route,
            tool_calls=ctx.tool_calls,
            partial=not completed,
        )
    except Exception as e:
        logger.error(
            f"Failed to persist assistant message for {ctx.conversation_id}: {e}"
        )
