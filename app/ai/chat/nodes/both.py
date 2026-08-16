"""Route BOTH: retrieve first, then run the tool loop over what came back."""

from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle
from app.ai.chat.tool_loop import run_tool_loop
from app.ai.tools.registry import TOOLS
from app.ai.prompts.rag import build_context_text
from app.ai.prompts.router import BOTH_SYSTEM_PROMPT
from app.ai.rag.pipeline import rag_pipeline
from app.core.tracing import drop_plumbing, join_tokens, set_run_inputs


@traceable(
    run_type="chain",
    name="rag_plus_tool_answer",
    process_inputs=drop_plumbing,
    reduce_fn=join_tokens,
)
async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]:
    """
    Retrieves resume context first (so the model can read a city out of it),
    then runs the same tool loop.
    """
    set_run_inputs(
        user_prompt=getattr(ctx, "user_prompt", ""),
        search_query=getattr(ctx, "search_query", ""),
    )

    retrieved_chunks = await rag_pipeline.retrieve(ctx.search_query)
    context_text = build_context_text(retrieved_chunks)

    messages = [
        SystemMessage(content=BOTH_SYSTEM_PROMPT),
        *ctx.history,
        HumanMessage(
            content=f"Resume context:\n{context_text}\n\nQuestion: {ctx.user_prompt}"
        ),
    ]

    async for token in run_tool_loop(messages, llms, ctx, TOOLS):
        yield token
