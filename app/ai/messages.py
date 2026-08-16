"""
Message helpers shared across the AI layer.

Pure functions over LangChain message objects — no model call, no database, no
event loop — so this module is safe to import from anywhere under app/ai/
without risking a cycle.
"""

from typing import Optional, Sequence

from langchain_core.messages import BaseMessage, HumanMessage


def content_to_text(content) -> str:
    """
    Flattens a message's content down to plain text.

    Groq hands back a plain string, but Gemini — which is what the fallback
    switches to whenever Groq rate-limits — can return a list of content
    parts instead. A raw list breaks in two places at once: Starlette calls
    .encode() on whatever the stream yields, and the history accumulator
    joins the tokens into one answer. Both need a str.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        pieces = []
        for part in content:
            if isinstance(part, str):
                pieces.append(part)
            elif isinstance(part, dict):
                pieces.append(part.get("text") or "")
        return "".join(pieces)

    if content is None:
        return ""

    return str(content)


def as_text(
    messages: Optional[Sequence[BaseMessage]],
    empty: str = "(no previous messages)",
) -> str:
    """
    Flattens messages into a plain transcript for the router prompt.

    The router is a small, fast classifier fed through a single prompt
    template, so it takes history as text rather than as a message list.

    Lives here rather than in app/memory/window.py — where it used to sit —
    because it touches no database at all, and importing it from there was the
    only reason the AI layer reached into the memory layer.
    """
    if not messages:
        return empty

    lines = []
    for message in messages:
        role = "User" if isinstance(message, HumanMessage) else "Assistant"
        lines.append(f"{role}: {content_to_text(message.content)}")
    return "\n".join(lines)
