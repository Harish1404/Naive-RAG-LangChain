import logging
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser

from app.prompts.rag_prompt import rag_chat_prompt, build_context_text
from app.core.config import settings
from app.rag.rag_pipeline import rag_pipeline

# logger lets us print debug/error messages to the console with proper labels
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# SECTION 1: ChatService (100% Pure LangChain streaming chat)
# ─────────────────────────────────────────────────────────

class ChatService:
    """
    Handles a single user chat message using 100% Pure LangChain architecture.
    Composes prompt templates, ChatGroq / ChatGoogleGenerativeAI fallbacks,
    and StrOutputParser via LCEL (|).
    Streams the reply back token-by-token using LangChain's .astream().
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

        # 3. Build LCEL chain using the pipe operator (|)
        self.chain = rag_chat_prompt | self.llm_with_fallbacks | StrOutputParser()

    async def chat(self):
        """
        Retrieves context from MongoDB Atlas and streams the response
        using LangChain's astream() through the LCEL pipeline.
        """
        try:
            # RAG step: pull the most relevant chunks from MongoDB Atlas
            retrieved_chunks = await rag_pipeline.retrieve(self.user_prompt)
            context_text = build_context_text(retrieved_chunks)

            # Stream tokens through the LCEL pipeline
            async for chunk in self.chain.astream({
                "context": context_text,
                "question": self.user_prompt
            }):
                yield chunk

        except Exception as e:
            logger.error(f"Chat pipeline execution failed: {e}")
            yield f"\n[ERROR: Chat service error — {e}]"




