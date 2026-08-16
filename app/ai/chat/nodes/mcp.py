"""Route MCP: read from the user's own connected accounts. No retrieval, no writes."""

import logging
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle, with_tools_for
from app.ai.chat.tool_loop import run_tool_loop
from app.ai.prompts.router import MCP_NOT_CONNECTED, MCP_SYSTEM_PROMPT
from app.ai.mcp.config import READ
from app.ai.tools.registry import TOOLS, tools_for_user
from app.core.tracing import drop_plumbing, join_tokens, set_run_inputs

logger = logging.getLogger(__name__)


@traceable(
    run_type="chain",
    name="mcp_answer",
    process_inputs=drop_plumbing,
    reduce_fn=join_tokens,
)
async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]:
    """
    Answers from whatever this user has connected — GitHub today.

    The tools are fetched here rather than when the turn was constructed, so a
    RAG or DIRECT question pays nothing for a connector round-trip it will never
    use. It costs this route one listing call, cached per user.
    """
    set_run_inputs(user_prompt=getattr(ctx, "user_prompt", ""))

    # READ explicitly: these tools come from GitHub's /readonly endpoint, so
    # the server itself will not hand back anything that writes. A question
    # that reads a poisoned issue body has nothing to be injected *into*.
    tools = await tools_for_user(ctx.user_id, READ)

    # tools_for_user always returns the shared tools, so "nothing connected"
    # means nothing came back beyond those.
    mcp_tools = [tool for tool in tools if tool not in TOOLS]

    if not mcp_tools:
        # Deliberately an answer, not an error. The router will pick MCP for a
        # user who never connected anything, and that has to read as a reply.
        logger.info(f"MCP route with no connected tools for {ctx.user_id!r}")
        yield MCP_NOT_CONNECTED
        return

    tool_names = ", ".join(tool.name for tool in mcp_tools)
    logger.info(f"MCP route for {ctx.user_id}: {len(mcp_tools)} tool(s) bound")

    # Per-request binding, never inside the cached build_models — see
    # with_tools_for for why that distinction is a security boundary.
    bound = with_tools_for(llms, mcp_tools)

    # A fresh list every call, same rule as the TOOL node: run_tool_loop
    # appends to what it is given and ctx.history must stay clean.
    messages = [
        SystemMessage(content=MCP_SYSTEM_PROMPT.format(tool_names=tool_names)),
        *ctx.history,
        HumanMessage(content=ctx.user_prompt),
    ]

    async for token in run_tool_loop(messages, bound, ctx, tools):
        yield token
