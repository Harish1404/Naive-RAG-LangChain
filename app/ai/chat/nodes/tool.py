"""Route TOOL: answer from a tool's result. No retrieval."""

from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle
from app.ai.chat.tool_loop import run_tool_loop
from app.ai.tools.registry import TOOLS
from app.ai.prompts.router import TOOL_SYSTEM_PROMPT
from app.core.tracing import drop_plumbing, join_tokens, set_run_inputs


@traceable(
    run_type="chain",
    name="tool_answer",
    process_inputs=drop_plumbing,
    reduce_fn=join_tokens,
)
async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]:
    """Answers using the weather tool only. No retrieval happens here."""
    set_run_inputs(user_prompt=getattr(ctx, "user_prompt", ""))

    # A fresh list every call: run_tool_loop appends to what it is given,
    # and ctx.history must never be mutated — it is replayed as-is and
    # would otherwise accumulate tool messages across turns.
    messages = [
        SystemMessage(content=TOOL_SYSTEM_PROMPT),
        *ctx.history,
        HumanMessage(content=ctx.user_prompt),
    ]

    async for token in run_tool_loop(messages, llms, ctx, TOOLS):
        yield token
