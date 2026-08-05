import logging

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser
from langsmith import traceable

from app.core.config import settings
from app.core.tracing import drop_self
from app.prompts.router_prompt import ROUTER_PROMPT

logger = logging.getLogger(__name__)


class QueryRouter:
    """
    Decides which path a user query should take before any work is done.

    It is a tiny LCEL chain — prompt | llm | parser — that asks a small, fast model
    to reply with a single word. That word is then validated against VALID_ROUTES.
    """

    VALID_ROUTES = {"RAG", "TOOL", "BOTH", "DIRECT"}

    # If the model returns something unusable, fall back to the app's main purpose.
    DEFAULT_ROUTE = "RAG"

    def __init__(self):
        # Classification must be deterministic and cheap, so this is a separate
        # model instance from the one ChatService uses for answering.
        primary_llm = ChatGroq(
            model="llama-3.1-8b-instant",
            groq_api_key=settings.groq_api_key,
            temperature=0,
            max_tokens=10
        )

        fallback_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0,
            max_output_tokens=10
        )

        llm = primary_llm.with_fallbacks([fallback_llm])

        # The whole router, as one LCEL pipeline
        self.chain = ROUTER_PROMPT | llm | StrOutputParser()

    @traceable(run_type="chain", name="route_query", process_inputs=drop_self)
    async def route(self, query: str) -> str:
        """
        Returns one of RAG / TOOL / BOTH / DIRECT.

        The inner LCEL chain traces itself as a child of this span, so the
        dashboard shows both the raw model output and the validated decision.
        """
        try:
            raw = await self.chain.ainvoke({"question": query})
            route = raw.strip().upper().strip(".,!:;\"'`")

            if route in self.VALID_ROUTES:
                return route

            logger.warning(
                f"Router returned an unrecognized value {raw!r}; "
                f"falling back to {self.DEFAULT_ROUTE}."
            )
        except Exception as e:
            logger.error(f"Router failed ({e}); falling back to {self.DEFAULT_ROUTE}.")

        return self.DEFAULT_ROUTE


# Module-level singleton, same pattern as app/rag/rag_pipeline.py
query_router = QueryRouter()
