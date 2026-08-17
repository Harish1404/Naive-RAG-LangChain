"""
Building the chat models, and paying their start-up costs before a user waits.

Nothing here knows what a turn is — it hands back clients and gets out of the
way.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI

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

    Constructing these is expensive and, crucially, *not* a one-off cold start.
    Stateless HTTP clients are built per token budget and shared across requests.
    """
    primary_llm = ChatMistralAI(
        model="mistral-small-latest",
        api_key=settings.mistral_api_key,
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


def with_tools_for(bundle: LLMBundle, tools: list) -> LLMBundle:
    """
    A copy of `bundle` whose tool-aware model also knows `tools`.

    This exists because MCP tools are **per user** while build_models is cached
    per token budget, and mixing those two is a cross-user credential leak:
    binding a user's GitHub tools inside build_models would store them in the
    lru_cache entry for `max_tokens`, and the next user with the same budget
    would be handed them. Two users, one cache entry, one GitHub account.

    So the expensive half stays cached and the per-user half happens here.
    Binding only attaches JSON schemas to an already-built client — no network
    call, no client construction — which is what makes it cheap enough to do on
    every request that needs it.

    Returns `bundle` unchanged when there is nothing to add, so the common case
    allocates nothing.
    """
    if not tools:
        return bundle

    combined = [*TOOLS, *tools]

    # bind_tools() on a RunnableWithFallbacks preserves the fallback chain on
    # langchain-core 1.5.3, so the Groq -> Gemini failover still applies to the
    # rebound model. Note this is the opposite of the constraint documented in
    # build_models above, which held for an older version and is why that
    # function still binds each model separately; do not "simplify" the two to
    # match without re-checking against the installed version.
    return LLMBundle(plain=bundle.plain, with_tools=bundle.plain.bind_tools(combined))


def warm_up_models() -> None:
    """Build both token-budget variants at startup rather than mid-request."""
    for budget in (DEFAULT_MAX_TOKENS, settings.voice_max_tokens):
        build_models(budget)


async def warm_up_llm() -> None:
    """Open the TLS connection to Mistral before the first real turn.

    Same reasoning as the STT warm-up in app/ai/voice/stt.py: the first
    request of a fresh process pays ~1-2s of TLS setup. Spending it here
    means the first user gets the same latency as everyone after them.

    Uses a lightweight /v1/models GET instead of a chat completion so it
    costs zero tokens and adds nothing to rate-limit counters.
    """
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.get(
                "https://api.mistral.ai/v1/models",
                headers={"Authorization": f"Bearer {settings.mistral_api_key}"},
                timeout=5.0,
            )
        logger.info("LLM connection warmed up (Mistral /models ping)")
    except Exception as e:
        logger.warning(f"LLM warm-up skipped: {e}")
