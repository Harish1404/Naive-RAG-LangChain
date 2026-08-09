from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    FLUX_AI = os.getenv("FLUX_AI")
    WEATHER_WEBHOOK_URL = os.getenv("WEATHER_WEBHOOK_URL")
    # LangSmith. Listed here for visibility only — the SDK reads these straight
    # out of os.environ, so it is the load_dotenv() call above that enables it.
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    LANGSMITH_ENDPOINT=os.getenv("LANGSMITH_ENDPOINT")
    # Required because the API key is org-scoped rather than workspace-scoped.
    # The SDK turns this into the X-Tenant-Id header; without it every
    # workspace-scoped call (projects, runs, run ingestion) returns 403.
    LANGSMITH_WORKSPACE_ID = os.getenv("LANGSMITH_WORKSPACE_ID")
    LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "default")

    MONGO_URL = os.getenv("MONGO_URL")
    DB_NAME = os.getenv("DB_NAME")

    # ── Conversation memory (window buffer) ──────────────────────────────────
    # How many past TURNS (a user message + its answer) are replayed to the
    # model. Tunable without a code edit, because the right number depends on
    # the model's context window and how chatty the answers are.
    WINDOW_K = int(os.getenv("WINDOW_K", "4"))
    # Long threads get a slightly wider window.
    WINDOW_K_LARGE = int(os.getenv("WINDOW_K_LARGE", "5"))
    LARGE_HISTORY_THRESHOLD = int(os.getenv("LARGE_HISTORY_THRESHOLD", "100"))

    @property
    def tracing_enabled(self) -> bool:
        return str(self.LANGSMITH_TRACING).lower() == "true" and bool(self.LANGSMITH_API_KEY)

    # lowercase aliases — this is what ChatService / ChainService actually read
    gemini_api_key = GEMINI_API_KEY
    groq_api_key = GROQ_API_KEY
    flux_ai = FLUX_AI
    weather_webhook_url = WEATHER_WEBHOOK_URL
    langsmith_api_key = LANGSMITH_API_KEY
    langsmith_tracing = LANGSMITH_TRACING
    langsmith_project = LANGSMITH_PROJECT

settings = Settings()

