from dotenv import load_dotenv
import os

load_dotenv()

class Settings:
    FRONTEND_URL = os.getenv("FRONTEND_URL")
    # Where *we* are reachable. Needed to build the OAuth redirect_uri, which
    # GitHub matches against the callback registered on the OAuth app — a
    # mismatch is rejected before the user ever sees a consent screen.
    BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY") or os.getenv("CEREBRES_API_KEY")
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
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

    # ── Auth ─────────────────────────────────────────────────────────────────
    # Clerk is the identity provider (who someone is); this backend is the
    # session authority (whether they may act right now). Clerk verifies the
    # sign-in, we mint our own short access token plus a rotating refresh token
    # and enforce is_banned/is_verified locally on every request.
    CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
    CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY")
    # Signing secret for the Clerk webhook endpoint. Without webhook sync, a
    # revocation on Clerk's side would never reach our refresh-token store.
    CLERK_WEBHOOK_SECRET = os.getenv("CLERK_WEBHOOK_SECRET")
    # `azp` allowlist: which origins may present a Clerk token to us.
    CLERK_AUTHORIZED_PARTIES = [
        origin
        for origin in (
            os.getenv("FRONTEND_URL"),
            "http://localhost:3000",
        )
        if origin
    ]

    JWT_SECRET = os.getenv("JWT_SECRET")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    # Short on purpose. The access token is verified without a database read,
    # so its lifetime is also the worst-case delay before a ban takes effect.
    ACCESS_TOKEN_TTL_MIN = int(os.getenv("ACCESS_TOKEN_TTL_MIN", "15"))
    REFRESH_TOKEN_TTL_DAYS = int(os.getenv("REFRESH_TOKEN_TTL_DAYS", "30"))

    ACCESS_COOKIE_NAME = os.getenv("ACCESS_COOKIE_NAME", "access_token")
    REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")
    # The refresh cookie is scoped to its own endpoint, so it is never sent on
    # ordinary API calls — far less exposure than a site-wide cookie.
    REFRESH_COOKIE_PATH = os.getenv("REFRESH_COOKIE_PATH", "/auth/refresh")
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    # localhost:3000 -> localhost:8000 is same-site (a port is not part of the
    # site), so "lax" works in development. Cross-domain production needs
    # "none", which browsers only honour together with Secure.
    COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
    COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None

    # ── Connectors (MCP) ─────────────────────────────────────────────────────
    # Our own GitHub OAuth app, registered at github.com/settings/developers.
    # The callback there must exactly match BACKEND_URL + /connectors/github/callback.
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    # Space-separated, the format GitHub's authorize endpoint expects.
    #
    # `repo` is required and there is no narrower option: GitHub has no
    # read-only private-repo scope, and the write workflow (create repository,
    # branch, push, open PR) needs write on private repos. `public_repo` would
    # cover public repos only, at the cost of reaching no private ones at all.
    #
    # Changing this later forces every already-connected user to re-consent.
    GITHUB_OAUTH_SCOPES = os.getenv("GITHUB_OAUTH_SCOPES", "repo read:org read:user")
    # GitHub's hosted remote MCP server, in two faces.
    #
    # READ is the /readonly variant and is what ordinary questions use. The
    # suffix is not decoration: measured against the live server, the plain
    # endpoint offers 44 tools of which 13 write (create_branch,
    # create_or_update_file, create_pull_request, delete_file,
    # merge_pull_request, ...), while /readonly offers 27 and none of them
    # write. That is enforced server-side, so it holds regardless of what the
    # OAuth scope permits and regardless of what our allowlist asks for.
    #
    # WRITE is the plain endpoint, reached only by the MCP_WRITE route, which
    # the router picks only when the user explicitly asks to create something.
    # A turn that merely reads a repository never has a write tool bound - see
    # the module docstring in app/ai/mcp/config.py for why that separation is
    # the point rather than an implementation detail.
    #
    # Other useful forms: /x/{toolset} narrows by area, and the X-MCP-Toolsets
    # header does the same. See docs/remote-server.md in github/github-mcp-server.
    GITHUB_MCP_READ_URL = os.getenv(
        "GITHUB_MCP_READ_URL", "https://api.githubcopilot.com/mcp/readonly"
    )
    GITHUB_MCP_WRITE_URL = os.getenv(
        "GITHUB_MCP_WRITE_URL", "https://api.githubcopilot.com/mcp/"
    )

    # base64 of 32 random bytes. Encrypts the stored OAuth token — see
    # app/core/crypto.py for why this cannot be a hash.
    CONNECTOR_ENC_KEY = os.getenv("CONNECTOR_ENC_KEY")

    # How long a user's MCP tool list is reused before being re-fetched.
    # Listing tools is a network round-trip on an otherwise hot path.
    MCP_TOOL_CACHE_TTL = int(os.getenv("MCP_TOOL_CACHE_TTL", "600"))
    # How long the signed OAuth `state` stays valid. Long enough to read a
    # consent screen, short enough that a leaked authorize URL goes stale.
    OAUTH_STATE_TTL_MIN = int(os.getenv("OAUTH_STATE_TTL_MIN", "5"))

    @property
    def auth_configured(self) -> bool:
        """False when the auth env vars are missing, so startup can say so."""
        return bool(self.CLERK_SECRET_KEY and self.JWT_SECRET)

    @property
    def github_connector_configured(self) -> bool:
        """False when the GitHub connector cannot work, so startup can say so."""
        return bool(
            self.GITHUB_CLIENT_ID
            and self.GITHUB_CLIENT_SECRET
            and self.CONNECTOR_ENC_KEY
        )

    @property
    def github_redirect_uri(self) -> str:
        """Built rather than configured, so it cannot drift from the route."""
        return f"{self.BACKEND_URL.rstrip('/')}/connectors/github/callback"

    @property
    def tracing_enabled(self) -> bool:
        return str(self.LANGSMITH_TRACING).lower() == "true" and bool(self.LANGSMITH_API_KEY)

    # lowercase aliases — this is what ChatService / ChainService actually read
    gemini_api_key = GEMINI_API_KEY
    groq_api_key = GROQ_API_KEY
    cerebras_api_key = CEREBRAS_API_KEY
    mistral_api_key = MISTRAL_API_KEY
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
    clerk_secret_key = CLERK_SECRET_KEY
    clerk_webhook_secret = CLERK_WEBHOOK_SECRET
    jwt_secret = JWT_SECRET
    jwt_algorithm = JWT_ALGORITHM
    github_client_id = GITHUB_CLIENT_ID
    github_client_secret = GITHUB_CLIENT_SECRET
    github_oauth_scopes = GITHUB_OAUTH_SCOPES
    github_mcp_read_url = GITHUB_MCP_READ_URL
    github_mcp_write_url = GITHUB_MCP_WRITE_URL
    connector_enc_key = CONNECTOR_ENC_KEY
    mcp_tool_cache_ttl = MCP_TOOL_CACHE_TTL
    oauth_state_ttl_min = OAUTH_STATE_TTL_MIN

settings = Settings()

