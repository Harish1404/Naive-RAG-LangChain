"""
The tool-calling loop, written out by hand.

Used by the TOOL and BOTH nodes. Kept out of both of them because it is the same
loop either way — the only difference between those two routes is what is in the
message list before it starts.
"""

import logging
from typing import AsyncIterator

from langchain_core.messages import ToolMessage
from langsmith import traceable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle
from app.ai.chat.streaming import stream_text
from app.ai.messages import content_to_text
from app.ai.tools.registry import get_tool
from app.core.tracing import join_tokens, summarize_messages

logger = logging.getLogger(__name__)


@traceable(
    run_type="chain",
    name="tool_loop",
    process_inputs=summarize_messages,
    reduce_fn=join_tokens,
)
async def run_tool_loop(
    messages: list,
    llms: LLMBundle,
    ctx: TurnContext,
) -> AsyncIterator[str]:
    """
    A single tool-call round-trip, using only langchain-core primitives:

      1. Ask the tool-aware model what to do.
      2. If it asked for tools, run each one and append a ToolMessage.
      3. Stream the final answer from the *plain* model, so it summarizes
         the tool results instead of calling the tool all over again.

    Because we own this loop, ToolMessage content is never yielded to the
    client — the raw webhook JSON can no longer leak into the stream.

    `messages` is mutated: the caller passes a list built for this turn, never
    ctx.history itself, which must stay clean for the next turn.
    """
    ai_msg = await llms.with_tools.ainvoke(messages)

    # The model answered directly without reaching for a tool.
    if not getattr(ai_msg, "tool_calls", None):
        text = content_to_text(ai_msg.content)
        if text:
            yield text
        return

    messages.append(ai_msg)

    for tool_call in ai_msg.tool_calls:
        name = tool_call.get("name")
        tool = get_tool(name)
        if tool is None:
            logger.warning(f"Model requested unknown tool {name!r}; skipping.")
            continue

        logger.info(f"Calling tool {name} with args {tool_call.get('args')}")

        # Kept for the stored message's metadata. Note this is recorded,
        # not replayed — see ConversationStore.append_message.
        ctx.tool_calls.append({"name": name, "args": tool_call.get("args")})

        try:
            result = await tool.ainvoke(tool_call["args"])
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            result = f"Tool error: {e}"

        messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    async for text in stream_text(llms.plain, messages):
        yield text
