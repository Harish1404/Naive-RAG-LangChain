"""
The four answer paths, and the map from a route name to the one that runs.

Exactly one node runs per turn:

    RAG    -> retrieve resume chunks, answer from them (no tools)
    TOOL   -> call the weather tool, answer from its result (no retrieval)
    BOTH   -> retrieve resume chunks AND call the weather tool
    DIRECT -> answer from the model's own knowledge (neither)

This is the fix for the old behaviour, where retrieval always ran and the
weather tool was always available, so both fired for every single question.
"""

from app.ai.chat.nodes import both, direct, rag, tool
from app.ai.chat.nodes.base import Node

NODES: dict[str, Node] = {
    "RAG": rag.stream,
    "TOOL": tool.stream,
    "BOTH": both.stream,
    "DIRECT": direct.stream,
}

# What runs when the route is missing or unrecognised. The router already
# guarantees one of the four (see QueryRouter.VALID_ROUTES), so this is the
# belt-and-braces case the old if/elif chain handled with its bare `else`.
DEFAULT_NODE: Node = direct.stream


def select(route: str | None) -> Node:
    """The node for this route, falling back rather than raising."""
    return NODES.get(route or "", DEFAULT_NODE)
