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

    ELEVEN_API = os.getenv("ELEVEN_API")

    # ── Voice mode ───────────────────────────────────────────────────────────
    # Flash v2.5 is the cheap, fast model: ~75ms to first byte and 0.5 credits
    # per character instead of 1. On the free tier's 10k credits/month that is
    # the difference between ~10 and ~20 thousand characters of speech.
    # Free accounts cannot use *library* voices over the API — the socket closes
    # with 1008 "Free users cannot use library voices". Verified working on this
    # key: Adam pNInz6obpgDQGcFmaJgB, Antoni ErXwobaYiN019PkySvjV,
    # Sarah EXAVITQu4vr4xnSDxMaL, Arnold VR6AewLTigWG4xSOukaG,
    # George JBFqnCBsd6RMkjVDRZzb, Jessica cgSgspJ2msm6clMCkdW9,
    # Daniel onwK4e9ZLuTAKqWW03F9. Rachel/Josh/Domi/Sam are library-gated.
    ELEVEN_VOICE_ID = os.getenv("ELEVEN_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
    ELEVEN_MODEL_ID = os.getenv("ELEVEN_MODEL_ID", "eleven_flash_v2_5")
    # pcm_24000 is NOT tier-gated (only pcm_44100/wav_44100 need Pro), which is
    # what lets the browser play raw frames through Web Audio with no decoder.
    ELEVEN_OUTPUT_FORMAT = os.getenv("ELEVEN_OUTPUT_FORMAT", "pcm_24000")
    TTS_SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "24000"))
    # What the browser's AudioWorklet is asked to produce. Whisper downsamples
    # to 16k internally anyway, so sending more than this is wasted bandwidth.
    MIC_SAMPLE_RATE = int(os.getenv("MIC_SAMPLE_RATE", "16000"))
    # Spoken answers are capped far below the text path's 500. Long answers are
    # bad voice UX, slow to first audio, and on the free tier a single 2000-char
    # reply costs 1000 of the month's 10000 credits.
    VOICE_MAX_TOKENS = int(os.getenv("VOICE_MAX_TOKENS", "120"))
    # Replays identical phrases from disk during development instead of paying
    # for them again. Turn off to measure real end-to-end latency.
    TTS_CACHE_ENABLED = os.getenv("TTS_CACHE_ENABLED", "true").lower() == "true"

    # ── Conversation memory (window buffer) ──────────────────────────────────
    # How many past TURNS (a user message + its answer) are replayed to the
    # model. Tunable without a code edit, because the right number depends on
    # the model's context window and how chatty the answers are.
    WINDOW_K = int(os.getenv("WINDOW_K", "4"))
    # Long threads get a slightly wider window.
    WINDOW_K_LARGE = int(os.getenv("WINDOW_K_LARGE", "5"))
    LARGE_HISTORY_THRESHOLD = int(os.getenv("LARGE_HISTORY_THRESHOLD", "100"))

    GITHUB_PAT = os.getenv("GITHUB_PAT")

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
    elevenlabs_api_key = ELEVEN_API
    eleven_voice_id = ELEVEN_VOICE_ID
    eleven_model_id = ELEVEN_MODEL_ID
    eleven_output_format = ELEVEN_OUTPUT_FORMAT
    tts_sample_rate = TTS_SAMPLE_RATE
    mic_sample_rate = MIC_SAMPLE_RATE
    voice_max_tokens = VOICE_MAX_TOKENS
    tts_cache_enabled = TTS_CACHE_ENABLED

settings = Settings()

