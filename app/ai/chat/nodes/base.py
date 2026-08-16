"""
What a node is.

A node answers one turn along one route. All four have the same shape:

    async def stream(ctx: TurnContext, llms: LLMBundle) -> AsyncIterator[str]

They read the turn out of `ctx`, borrow the models from `llms`, and yield plain
text. A node never touches the database, never calls the router, and never
imports another node — which is what makes each one readable on its own, and
what makes adding a fifth route a new file rather than a new branch.
"""

from typing import AsyncIterator, Callable

from app.ai.chat.context import TurnContext
from app.ai.chat.models import LLMBundle

Node = Callable[[TurnContext, LLMBundle], AsyncIterator[str]]
