"""
The one loop that turns a model's chunk stream into plain text tokens.

Three places did this identically — the RAG node, the DIRECT node, and the tail
of the tool loop. It is small, but getting it wrong is not: a chunk whose
content is a Gemini part-list has to be flattened before it reaches Starlette,
and an empty chunk must not be yielded at all.
"""

from typing import Any, AsyncIterator

from app.ai.messages import content_to_text


async def stream_text(llm: Any, messages: list) -> AsyncIterator[str]:
    """Stream `messages` through `llm`, yielding non-empty plain-text tokens."""
    async for chunk in llm.astream(messages):
        text = content_to_text(chunk.content)
        if text:
            yield text
