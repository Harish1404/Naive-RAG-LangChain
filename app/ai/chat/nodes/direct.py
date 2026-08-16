"""Route DIRECT: answer from the model's own knowledge. No retrieval, no tools."""

from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle
from app.ai.chat.streaming import stream_text
from app.ai.prompts.router import DIRECT_SYSTEM_PROMPT
from app.core.tracing import drop_plumbing, join_tokens, set_run_inputs


@traceable(
    run_type="chain",
    name="direct_answer",
    process_inputs=drop_plumbing,
    reduce_fn=join_tokens,
)
async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]:
    """Answers from the model's own knowledge. No retrieval, no tools."""
    set_run_inputs(user_prompt=ctx.user_prompt)

    messages = [
        SystemMessage(content=DIRECT_SYSTEM_PROMPT),
        *ctx.history,
        HumanMessage(content=ctx.user_prompt),
    ]

    async for text in stream_text(llms.plain, messages):
        yield text
