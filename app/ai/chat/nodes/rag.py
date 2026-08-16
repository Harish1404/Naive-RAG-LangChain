"""Route RAG: answer strictly from retrieved resume chunks. No tools."""

from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle
from app.ai.chat.streaming import stream_text
from app.ai.prompts.rag import RAG_SYSTEM_PROMPT, build_context_text
from app.ai.rag.pipeline import rag_pipeline
from app.core.tracing import drop_plumbing, join_tokens, set_run_inputs


@traceable(
    run_type="chain",
    name="rag_answer",
    process_inputs=drop_plumbing,
    reduce_fn=join_tokens,
)
async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]:
    """Answers strictly from resume chunks retrieved out of MongoDB Atlas."""
    set_run_inputs(user_prompt=ctx.user_prompt, search_query=ctx.search_query)

    # Retrieval uses the router's rewritten question, not the raw one: a
    # follow-up such as "and where did he study?" has nothing to embed.
    retrieved_chunks = await rag_pipeline.retrieve(ctx.search_query)
    context_text = build_context_text(retrieved_chunks)

    messages = [
        SystemMessage(content=RAG_SYSTEM_PROMPT),
        *ctx.history,
        HumanMessage(content=f"Context:\n{context_text}\n\nQuestion: {ctx.user_prompt}"),
    ]

    async for text in stream_text(llms.plain, messages):
        yield text
