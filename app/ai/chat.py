import json
import logging
import traceback

from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langsmith import traceable

from app.core.tracing import (
    summarize_messages,
    join_tokens,
    set_run_inputs,
    set_run_metadata,
)
from app.prompts.rag_prompt import RAG_SYSTEM_PROMPT, build_context_text
from app.prompts.router_prompt import (
    TOOL_SYSTEM_PROMPT,
    BOTH_SYSTEM_PROMPT,
    DIRECT_SYSTEM_PROMPT,
)
from app.core.config import settings
from app.rag.rag_pipeline import rag_pipeline
from app.ai.router import query_router
from app.tools.weather import get_weather

# logger lets us print debug/error messages to the console with proper labels
logger = logging.getLogger(__name__)


def format_sse_event(event_type: str, content: str) -> str:
    """Formats event data into standard Server-Sent Events (SSE) string."""
    return f"data: {json.dumps({'type': event_type, 'content': content})}\n\n"


# ─────────────────────────────────────────────────────────
# SECTION 1: ChatService (100% Pure LangChain streaming chat)
# ─────────────────────────────────────────────────────────

class ChatService:
    """
    Handles a single user chat message.

    A router first classifies the query, then exactly one path runs:

        RAG    -> retrieve resume chunks, answer from them (no tools)
        TOOL   -> call the weather tool, answer from its result (no retrieval)
        BOTH   -> retrieve resume chunks AND call the weather tool
        DIRECT -> answer from the model's own knowledge (neither)

    This is the fix for the old behaviour, where retrieval always ran and the
    weather tool was always available, so both fired for every single question.
    """

    def __init__(self, model_type: str, user_prompt: str):
        self.user_prompt = user_prompt

        self.gemini_key = settings.gemini_api_key
        self.groq_key   = settings.groq_api_key

        # 1. Initialize official LangChain models directly
        primary_llm = ChatGroq(
            model="llama-3.1-8b-instant",
            groq_api_key=self.groq_key,
            temperature=0.7,
            max_tokens=500
        )

        fallback_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=self.gemini_key,
            temperature=0.7,
            max_output_tokens=500
        )

        # 2. Add automatic fallback model
        self.llm_with_fallbacks = primary_llm.with_fallbacks([fallback_llm])

        # 3. A tool-aware variant of the same pair.
        #    Note the order: bind_tools() must be applied to each *model* first,
        #    because with_fallbacks() returns a RunnableWithFallbacks, which has
        #    no bind_tools() method of its own.
        self.llm_with_tools = primary_llm.bind_tools([get_weather]).with_fallbacks(
            [fallback_llm.bind_tools([get_weather])]
        )

    # ── Entry point ──────────────────────────────────────────────────────────

    @traceable(
        run_type="chain",
        name="chatbot_request",
        reduce_fn=join_tokens,
    )
    async def chat(self):
        """
        Routes the query, then streams plain text tokens from the chosen path.

        This is also the ROOT of the LangSmith trace. Every LLM call, tool call
        and retrieval below it nests under this one span, which is what turns a
        handful of disconnected dashboard rows into a single request tree.
        """
        # This method takes no arguments other than `self`, which langsmith
        # strips — so the question has to be published onto the span by hand,
        # or the dashboard would show the answer with no sign of the input.
        set_run_inputs(user_prompt=self.user_prompt)

        try:
            route = await query_router.route(self.user_prompt)
            logger.info(f"Router selected: {route} for query: {self.user_prompt!r}")

            # The route is only known now, so it is attached at runtime rather
            # than declared on the decorator. Lets you filter the dashboard by
            # metadata.route to compare paths.
            set_run_metadata(route=route)

            if route == "RAG":
                stream = self._rag_stream()
            elif route == "TOOL":
                stream = self._tool_stream()
            elif route == "BOTH":
                stream = self._both_stream()
            else:
                stream = self._direct_stream()

            async for token in stream:
                yield token

        except Exception as e:
            logger.error(f"Chat pipeline execution failed: {e}\n{traceback.format_exc()}")
            yield f"\n[ERROR: Chat service error — {e}]"

    # ── Route: RAG ───────────────────────────────────────────────────────────

    @traceable(
        run_type="chain",
        name="rag_answer",
        reduce_fn=join_tokens,
    )
    async def _rag_stream(self):
        """Answers strictly from resume chunks retrieved out of MongoDB Atlas."""
        set_run_inputs(user_prompt=self.user_prompt)

        retrieved_chunks = await rag_pipeline.retrieve(self.user_prompt)
        context_text = build_context_text(retrieved_chunks)

        messages = [
            SystemMessage(content=RAG_SYSTEM_PROMPT),
            HumanMessage(content=f"Context:\n{context_text}\n\nQuestion: {self.user_prompt}")
        ]

        async for chunk in self.llm_with_fallbacks.astream(messages):
            if chunk.content:
                yield chunk.content

    # ── Route: TOOL ──────────────────────────────────────────────────────────

    @traceable(
        run_type="chain",
        name="tool_answer",
        reduce_fn=join_tokens,
    )
    async def _tool_stream(self):
        """Answers using the weather tool only. No retrieval happens here."""
        set_run_inputs(user_prompt=self.user_prompt)

        messages = [
            SystemMessage(content=TOOL_SYSTEM_PROMPT),
            HumanMessage(content=self.user_prompt)
        ]

        async for token in self._run_tool_loop(messages):
            yield token

    # ── Route: BOTH ──────────────────────────────────────────────────────────

    @traceable(
        run_type="chain",
        name="rag_plus_tool_answer",
        reduce_fn=join_tokens,
    )
    async def _both_stream(self):
        """
        Retrieves resume context first (so the model can read a city out of it),
        then runs the same tool loop.
        """
        set_run_inputs(user_prompt=self.user_prompt)

        retrieved_chunks = await rag_pipeline.retrieve(self.user_prompt)
        context_text = build_context_text(retrieved_chunks)

        messages = [
            SystemMessage(content=BOTH_SYSTEM_PROMPT),
            HumanMessage(content=f"Resume context:\n{context_text}\n\nQuestion: {self.user_prompt}")
        ]

        async for token in self._run_tool_loop(messages):
            yield token

    # ── Route: DIRECT ────────────────────────────────────────────────────────

    @traceable(
        run_type="chain",
        name="direct_answer",
        reduce_fn=join_tokens,
    )
    async def _direct_stream(self):
        """Answers from the model's own knowledge. No retrieval, no tools."""
        set_run_inputs(user_prompt=self.user_prompt)

        messages = [
            SystemMessage(content=DIRECT_SYSTEM_PROMPT),
            HumanMessage(content=self.user_prompt)
        ]

        async for chunk in self.llm_with_fallbacks.astream(messages):
            if chunk.content:
                yield chunk.content

    # ── The tool-calling loop, written out by hand ───────────────────────────

    @traceable(
        run_type="chain",
        name="tool_loop",
        process_inputs=summarize_messages,
        reduce_fn=join_tokens,
    )
    async def _run_tool_loop(self, messages: list):
        """
        A single tool-call round-trip, using only langchain-core primitives:

          1. Ask the tool-aware model what to do.
          2. If it asked for tools, run each one and append a ToolMessage.
          3. Stream the final answer from the *plain* model, so it summarizes
             the tool results instead of calling the tool all over again.

        Because we own this loop, ToolMessage content is never yielded to the
        client — the raw webhook JSON can no longer leak into the stream.
        """
        ai_msg = await self.llm_with_tools.ainvoke(messages)

        # The model answered directly without reaching for a tool.
        if not getattr(ai_msg, "tool_calls", None):
            if ai_msg.content:
                yield ai_msg.content
            return

        messages.append(ai_msg)

        for tool_call in ai_msg.tool_calls:
            name = tool_call.get("name")
            if name != get_weather.name:
                logger.warning(f"Model requested unknown tool {name!r}; skipping.")
                continue

            logger.info(f"Calling tool {name} with args {tool_call.get('args')}")
            try:
                result = await get_weather.ainvoke(tool_call["args"])
            except Exception as e:
                logger.error(f"Tool {name} failed: {e}")
                result = f"Tool error: {e}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        async for chunk in self.llm_with_fallbacks.astream(messages):
            if chunk.content:
                yield chunk.content

    # ────────────────────────────────────────────────────────────────────────
    # OPTIONAL: SSE EVENT STREAMING (Uncomment when connecting to a Frontend UI)
    # ────────────────────────────────────────────────────────────────────────
    # async def chat_sse(self):
    #     """
    #     Same routing as chat(), but emits rich SSE events (status updates and
    #     text tokens) instead of bare text, for a Frontend UI to render.
    #     """
    #     try:
    #         yield format_sse_event("status", "Understanding your question...")
    #         route = await query_router.route(self.user_prompt)
    #         yield format_sse_event("status", f"Route selected: {route}")
    #
    #         if route == "RAG":
    #             yield format_sse_event("status", "Searching knowledge base...")
    #             stream = self._rag_stream()
    #         elif route == "TOOL":
    #             yield format_sse_event("status", "Checking the weather...")
    #             stream = self._tool_stream()
    #         elif route == "BOTH":
    #             yield format_sse_event("status", "Searching knowledge base and checking the weather...")
    #             stream = self._both_stream()
    #         else:
    #             yield format_sse_event("status", "Thinking...")
    #             stream = self._direct_stream()
    #
    #         async for token in stream:
    #             yield format_sse_event("token", token)
    #
    #         yield format_sse_event("done", "Response complete")
    #
    #     except Exception as e:
    #         logger.error(f"Chat pipeline execution failed: {e}\n{traceback.format_exc()}")
    #         yield format_sse_event("error", f"Chat service error — {e}")
