"""
Route MCP_WRITE: create things in the user's own accounts.

The only node in the app that can change anything outside our own database, and
the only one bound to GitHub's writable endpoint. It runs when the user has
explicitly asked to create a repository, branch, push, or open a pull request —
never on a turn that is merely answering a question.

That separation is the point. See the module docstring in app/ai/mcp/config.py:
the model reads issue bodies and file contents that anyone can publish, so a
turn that both ingests untrusted text and holds `push_files` is a working prompt
injection. Reading happens on the MCP route, where the server offers no write
tool at all; writing happens here, where the user asked for it in so many words.
"""

import logging
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle, with_tools_for
from app.ai.chat.tool_loop import run_tool_loop
from app.ai.mcp.config import WRITE
from app.ai.prompts.router import MCP_NOT_CONNECTED, MCP_WRITE_SYSTEM_PROMPT
from app.ai.tools.registry import TOOLS, tools_for_user
from app.core.tracing import drop_plumbing, join_tokens, set_run_inputs

logger = logging.getLogger(__name__)


@traceable(
    run_type="chain",
    name="mcp_write_answer",
    process_inputs=drop_plumbing,
    reduce_fn=join_tokens,
)
async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]:
    """Creates a repository, branch, commit or pull request, then reports back."""
    set_run_inputs(user_prompt=getattr(ctx, "user_prompt", ""))

    tools = await tools_for_user(ctx.user_id, WRITE)
    mcp_tools = [tool for tool in tools if tool not in TOOLS]

    if not mcp_tools:
        logger.info(f"MCP_WRITE route with no connected tools for {ctx.user_id!r}")
        yield MCP_NOT_CONNECTED
        return

    tool_names = ", ".join(tool.name for tool in mcp_tools)

    # Logged at a level worth keeping: this is the one route that can change
    # something the user cannot trivially undo, so there should always be a line
    # in the log saying it ran and for whom.
    logger.info(
        f"MCP_WRITE route for {ctx.user_id}: {len(mcp_tools)} tool(s) bound "
        f"[{tool_names}]"
    )

    bound = with_tools_for(llms, mcp_tools)

    messages = [
        SystemMessage(content=MCP_WRITE_SYSTEM_PROMPT.format(tool_names=tool_names)),
        *ctx.history,
        HumanMessage(content=ctx.user_prompt),
    ]

    async for token in run_tool_loop(messages, bound, ctx, tools):
        yield token
