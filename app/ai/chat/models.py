"""
Building the chat models, and paying their start-up costs before a user waits.

Nothing here knows what a turn is — it hands back clients and gets out of the
way.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from app.ai.tools.registry import TOOLS
from app.core.config import settings

logger = logging.getLogger(__name__)

# The token budget for a typed answer. Voice uses settings.voice_max_tokens,
# which is far lower — see TurnContext.
DEFAULT_MAX_TOKENS = 500


@dataclass(frozen=True)
class LLMBundle:
    """The two models a turn needs: one plain, one tool-aware.

    Handed to every node, so a node never constructs a client of its own and
    the token budget is decided in exactly one place.
    """

    plain: Any
    with_tools: Any


@lru_cache(maxsize=4)
def build_models(max_tokens: int) -> LLMBundle:
    """The model pair for a given token budget, built once per process.

    Constructing these is expensive and, crucially, *not* a one-off cold start:
    measured here, ChatGoogleGenerativeAI takes ~740ms and ChatGroq ~490ms
    EVERY time, so building them per request put a flat ~1.2s in front of every
    answer — voice and text alike — before a single byte was sent to any API.

    They are stateless HTTP clients, so one set per token budget is safe to
    share across requests, the same way app/ai/router/query_router.py already
    keeps a module-level singleton. Cached on max_tokens because that is the
    only thing that varies (500 for text, ~120 for voice), which means two
    entries.
    """
    primary_llm = ChatGroq(
        model="llama-3.1-8b-instant",
        groq_api_key=settings.groq_api_key,
        temperature=0.7,
        max_tokens=max_tokens,
    )

    fallback_llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.7,
        max_output_tokens=max_tokens,
    )

    llm_with_fallbacks = primary_llm.with_fallbacks([fallback_llm])

    # Note the order: bind_tools() must be applied to each *model* first,
    # because with_fallbacks() returns a RunnableWithFallbacks, which has no
    # bind_tools() method of its own.
    llm_with_tools = primary_llm.bind_tools(TOOLS).with_fallbacks(
        [fallback_llm.bind_tools(TOOLS)]
    )

    return LLMBundle(plain=llm_with_fallbacks, with_tools=llm_with_tools)


def warm_up_models() -> None:
    """Build both token-budget variants at startup rather than mid-request."""
    for budget in (DEFAULT_MAX_TOKENS, settings.voice_max_tokens):
        build_models(budget)


async def warm_up_llm() -> None:
    """Open the connection to Groq's chat endpoint before the first real turn.

    Same reasoning as the STT warm-up in app/ai/voice/stt.py, and measurably
    worth it: the first turn of a fresh process saw first-audio at ~2.4s against
    ~1.3s for every turn after, and the difference was almost entirely the
    first chat/completions call paying for TLS setup.
    """
    try:
        llms = build_models(settings.voice_max_tokens)
        async for _ in llms.plain.astream([HumanMessage(content="hi")]):
            break  # one token is enough to establish the connection
        logger.info("LLM connection warmed up")
    except Exception as e:
        logger.warning(f"LLM warm-up skipped: {e}")
