"""
The orchestrator: one user message in, a stream of answer tokens out.

Everything this file does is coordination. It holds no prompt, builds no model,
writes no query and implements no route — those live in models.py, prompts/,
persistence.py and nodes/ respectively. What is left is the shape of a turn:

    route it  ->  pick the node  ->  stream its tokens  ->  persist the answer

The service is also the memory boundary: it is handed the conversation's recent
history to replay, and it is what writes the finished answer back.
"""

import logging
import traceback

from langchain_core.messages import BaseMessage
from langsmith import traceable

from app.ai.chat import nodes
from app.ai.chat.context import TurnContext
from app.ai.chat.models import build_models
from app.ai.chat.persistence import persist_answer, schedule_persist
from app.ai.router.query_router import query_router
from app.core.tracing import join_tokens, set_run_inputs, set_run_metadata

logger = logging.getLogger(__name__)


class ChatService:
    """
    Handles a single user chat message.

    A router first classifies the query, then exactly one node runs — see
    app/ai/chat/nodes/__init__.py for the four of them.
    """

    def __init__(
        self,
        user_prompt: str,
        conversation_id: str,
        history: list[BaseMessage] | None = None,
        voice_mode: bool = False,
        user_id: str = "",
    ):
        self.ctx = TurnContext(
            user_prompt=user_prompt,
            conversation_id=conversation_id,
            user_id=user_id,
            # Already trimmed to the last k turns by the caller.
            history=list(history or []),
            voice_mode=voice_mode,
        )

        # Shared across requests — see build_models for why this is not done
        # inline here any more.
        self.llms = build_models(self.ctx.max_tokens)

    # ── Entry point ──────────────────────────────────────────────────────────

    @traceable(
        run_type="chain",
        name="chatbot_request",
        reduce_fn=join_tokens,
    )
    async def chat(self):
        """
        Routes the query, then streams plain text tokens from the chosen node.

        This is also the ROOT of the LangSmith trace. Every LLM call, tool call
        and retrieval below it nests under this one span, which is what turns a
        handful of disconnected dashboard rows into a single request tree.
        """
        # This method takes no arguments other than `self`, which langsmith
        # strips — so the question has to be published onto the span by hand,
        # or the dashboard would show the answer with no sign of the input.
        set_run_inputs(
            user_prompt=self.ctx.user_prompt,
            conversation_id=self.ctx.conversation_id,
        )

        # Nothing else buffers the answer — the tokens are streamed straight to
        # the client — so it is collected here to be written to MongoDB.
        parts: list[str] = []
        completed = False
        abandoned = False

        try:
            await self._route()

            async for token in nodes.select(self.ctx.route)(self.ctx, self.llms):
                parts.append(token)
                yield token

            completed = True

        except GeneratorExit:
            # The client went away mid-answer and this generator is being torn
            # down. Flagged rather than handled here, so the finally below can
            # tell an abandoned stream apart from a finished one.
            abandoned = True
            raise

        except Exception as e:
            logger.error(f"Chat pipeline execution failed: {e}\n{traceback.format_exc()}")
            yield f"\n[ERROR: Chat service error — {e}]"

        finally:
            answer = "".join(parts)

            if abandoned:
                # Cannot await here. An abandoned async generator is finalized
                # by the event loop after aclose() has already returned, and an
                # await at that point is cancelled — the write would be issued
                # and then silently dropped. Handing it to an independent task
                # gets it off this dying frame. Best-effort by nature.
                schedule_persist(self.ctx, answer)
            else:
                # Normal and error paths still have a live request behind them,
                # so this is awaited: the next turn must not be able to load
                # history before this answer has landed.
                await persist_answer(self.ctx, answer, completed)

    # ── Routing ──────────────────────────────────────────────────────────────

    async def _route(self) -> None:
        """Classifies the turn and records the decision onto the context."""
        decision = await query_router.route(self.ctx.user_prompt, self.ctx.history)
        self.ctx.route = decision.route
        self.ctx.search_query = decision.standalone_question

        logger.info(
            f"Router selected: {self.ctx.route} for query: {self.ctx.user_prompt!r} "
            f"(searching for: {self.ctx.search_query!r})"
        )

        # The route is only known now, so it is attached at runtime rather
        # than declared on the decorator. Lets you filter the dashboard by
        # metadata.route to compare paths. thread_id is what groups every
        # turn of one conversation into a single LangSmith thread.
        set_run_metadata(
            route=self.ctx.route,
            conversation_id=self.ctx.conversation_id,
            thread_id=self.ctx.conversation_id,
            standalone_question=self.ctx.search_query,
            history_messages=len(self.ctx.history),
        )
