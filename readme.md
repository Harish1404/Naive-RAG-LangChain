# LangChain RAG & Multi-Modal AI System

A production-grade, asynchronous Retrieval-Augmented Generation (RAG) and multi-modal AI backend built with **FastAPI**, **LangChain**, and **MongoDB Atlas**.

This system features dynamic query routing, hybrid vector & keyword retrieval fused via **Reciprocal Rank Fusion (RRF)**, automatic fallback across dual LLM providers (**Groq Llama 3.1 8B** + **Google Gemini 2.5 Flash**), tool calling with external webhooks, 3-stage LCEL document transformation chains, and multi-modal capabilities (voice STT/TTS & image generation).

---

## 📖 Architecture & Documentation Index

Comprehensive technical documentation is available in the [`docs/`](file:///c:/Users/haris/Documents/Projects/Langchain-RAG/docs) directory:

- 🏗️ **[System Architecture](docs/architecture.md)** — Complete component breakdown and system-wide Mermaid diagram.
- 🔄 **[RAG & App Workflows](docs/workflow.md)** — Detailed sequence flows for startup ingestion, hybrid retrieval, tool execution, and streaming responses.
- ✂️ **[Chunking Strategy](docs/chunking.md)** — Recursive text splitting, parameter choices, and incremental deduplication logic.
- 🚀 **[Advanced RAG Concepts](docs/advanced-rag.md)** — Hybrid search, query expansion, re-ranking, and context compression.
- 🤖 **[Agentic RAG Concepts](docs/agentic-rag.md)** — Planner loops, tool selection, reflection, and self-correction.
- 🕸️ **[Graph RAG Concepts](docs/graph-rag.md)** — Knowledge graphs, entity-relation extraction, and graph traversal.
- 🧩 **[Modular RAG Concepts](docs/modular-rag.md)** — Decoupled modules and flexible pipeline architectures.

---

## ✨ Key Features & Capabilities

### 1. Dynamic Query Routing
Before executing any retrieval or LLM generation, an ultra-fast classification chain (`QueryRouter`) categorizes incoming prompts into one of four distinct execution routes:
- **`RAG`**: Performs hybrid search over uploaded knowledge base documents in MongoDB Atlas (no tools).
- **`TOOL`**: Executes external tools directly (e.g. `get_weather` webhook) without performing document retrieval.
- **`BOTH`**: Retrieves knowledge base context first to resolve entity/location details, then executes the tool call with the extracted context.
- **`DIRECT`**: Answers directly from the LLM's parametric knowledge for general conversation.

### 2. MongoDB Atlas Hybrid Search & RRF
- **Vector Search (`$vectorSearch`)**: Dense semantic search using Google's `models/gemini-embedding-001` (768 dimensions) with Cosine similarity.
- **Keyword Search (`$search`)**: Sparse text search leveraging Atlas Search (BM25 algorithm).
- **Reciprocal Rank Fusion (RRF)**: Combines ranked vector and keyword candidate lists into a single deduplicated, highly accurate context payload.
- **Automatic Index Management**: Automatically provisions `vector_index` and `keyword_index` on MongoDB Atlas via PyMongo `SearchIndexModel` on boot.

### 3. Dual LLM High Availability Engine
- **Primary LLM**: Groq `llama-3.1-8b-instant` (ultra-low latency).
- **Fallback LLM**: Google Gemini `gemini-2.5-flash` (high quality, high context).
- Integrated seamlessly using LangChain's `with_fallbacks()` runnable wrapper to protect against rate limits and outage events.

### 4. Incremental Ingestion & Zero-Cost Boot
- On server startup (`app/main.py` lifespan), the system scans the `uploads/` directory.
- It checks existing document chunk IDs in MongoDB Atlas before embedding.
- **Only new or updated chunks** are passed to the embedding API, guaranteeing zero redundant embedding cost and fast boot times.

### 5. Multi-Modal & Specialized AI Modules
- **3-Stage LCEL Chain (`app/ai/chain.py`)**: Concept extraction (JSON parser) → Concept enrichment → Markdown report generation.
- **Image Generation (`app/ai/image.py`)**: Generates images using LiteLLM and Gemini Imagen 3 (`gemini/Gemini 2.5 Flash Preview Image`), returning PIL image instances.
- **Voice Engine (`app/ai/voice.py`)**: Speech-to-Text via Groq Whisper Turbo (`whisper-large-v3-turbo`) and Text-to-Speech via `edge_tts` (`en-IN-PrabhatNeural`).

---

## 📁 Repository Structure

```
Langchain-RAG/
├── app/
│   ├── ai/
│   │   ├── chain.py          # 3-Stage LCEL Concept Extraction & Enrichment Pipeline
│   │   ├── chat.py           # Core ChatService, Router integration & Tool-calling loop
│   │   ├── image.py          # Image generation via LiteLLM (Gemini Imagen 3)
│   │   ├── router.py         # Lightweight QueryRouter classification chain
│   │   └── voice.py          # Speech-to-Text (Whisper) & Text-to-Speech (EdgeTTS)
│   ├── core/
│   │   └── config.py         # Centralized Settings & environment variable configuration
│   ├── db/
│   │   └── mongodb.py        # Motor async MongoDB client & connection lifecycle
│   ├── prompts/
│   │   ├── chain_prompts.py  # Prompts for 3-stage chain pipeline
│   │   ├── rag_prompt.py    # System prompts & context formatters for RAG
│   │   └── router_prompt.py # System prompts for Router & route-specific models
│   ├── rag/
│   │   ├── data_processor.py # File loader (.pdf, .txt, .md) & RecursiveCharacterTextSplitter
│   │   ├── embeddings.py     # Gemini GoogleGenerativeAIEmbeddings (768d)
│   │   ├── rag_pipeline.py   # Ingestion & retrieval orchestrator singleton
│   │   └── vector_store.py   # MongoDB Atlas Vector/Keyword search & RRF implementation
│   ├── memory/
│   │   ├── store.py          # MongoDB persistence for conversations & messages
│   │   └── window.py         # Window buffer: last k turns -> LangChain messages
│   ├── schemas/
│   │   └── chat.py           # Pydantic request/response models
│   ├── routes/
│   │   ├── chatbot.py        # FastAPI APIRouter streaming endpoint (/chatbot)
│   │   └── conversations.py  # Conversation CRUD (new chat, list, transcript, rename, delete)
│   └── main.py               # FastAPI app initialization, lifespan handler & health routes
├── docs/                     # Technical architecture, workflow, and RAG guides
├── uploads/                  # Input directory for knowledge base documents (.pdf, .txt, .md)
├── .env                      # Environment secrets (API keys & MongoDB connection URI)
├── readme.md                 # Project Overview & System Documentation
├── requirements.txt          # Python dependencies
└── server.py                 # Server startup script (Uvicorn runner)
```

---

## ⚙️ Environment Configuration

Create a `.env` file in the project root with the following keys:

```env
# LLM & Embedding API Keys
GEMINI_API_KEY=your_google_gemini_api_key
GROQ_API_KEY=your_groq_api_key
FLUX_AI=optional_flux_key

# MongoDB Atlas Configuration
MONGO_URL=mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority
DB_NAME=rag_db

# External Tools & Webhooks
WEATHER_WEBHOOK_URL=https://your-webhook-endpoint.com

# LangSmith Tracing (optional — tracing is off unless LANGSMITH_TRACING=true)
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=your_project_name
# Required when the API key is org-scoped rather than workspace-scoped
LANGSMITH_WORKSPACE_ID=your_workspace_id

# Conversation memory window (all optional — defaults shown)
WINDOW_K=4                    # turns replayed to the model
WINDOW_K_LARGE=5              # turns once a thread gets long
LARGE_HISTORY_THRESHOLD=100   # turn count at which the wider window kicks in
```

---

## 🚀 Running the Server

1. **Activate Virtual Environment**:
   ```bash
   venv\Scripts\activate   # Windows
   source venv/bin/activate # Linux/macOS
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the FastAPI Server**:
   ```bash
   python server.py
   ```
   Or directly via Uvicorn:
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

4. **Verify Health Check**:
   Open `http://127.0.0.1:8000/health` in your browser.

---

## 📡 API Endpoint Reference

### `POST /chatbot`
Streams the answer back as plain text tokens.

- **JSON Body**:
  - `user_prompt` (`str`, required): The question or command for the assistant.
  - `conversation_id` (`str`, optional): Continue an existing thread. Omit it to start a new one.
  - `user_id` (`str`, optional): Defaults to `"default_user"`.

- **Response Header**:
  - `X-Conversation-Id`: The thread this message landed in — read it on the first
    message to learn the id of a newly created conversation.

- **Example Request**:
  ```bash
  # New chat (id comes back in the header)
  curl -N -D - -X POST "http://127.0.0.1:8000/chatbot" \
       -H "Content-Type: application/json" \
       -d '{"user_prompt": "Who is Harish?"}'

  # Continue that chat — follow-ups can rely on the previous turns
  curl -N -X POST "http://127.0.0.1:8000/chatbot" \
       -H "Content-Type: application/json" \
       -d '{"conversation_id": "conv_...", "user_prompt": "what are his skills?"}'
  ```

### Conversation management

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/conversations` | Start a new chat explicitly |
| `GET` | `/conversations?user_id=&limit=&skip=` | List threads, most recently active first |
| `GET` | `/conversations/{id}?limit=&before_seq=` | Full transcript, oldest message first |
| `PATCH` | `/conversations/{id}` | Rename (`{"title": "..."}`) |
| `DELETE` | `/conversations/{id}` | Soft delete |

---

## 🧠 Conversation Memory

Chat history is persisted in MongoDB across two collections — `conversations`
(one per thread: title, owner, counters) and `messages` (one per turn, ordered
by `seq`).

On each request the last **k turns** are replayed to the model — a window
buffer, equivalent to the old `ConversationBufferWindowMemory(k=...)`, but
implemented natively over the async Motor client. (LangChain 1.0 removed
`langchain.memory` entirely, and its MongoDB backend was blocking pymongo,
which would stall the event loop in these async endpoints.) `k` defaults to 4
and widens to 5 once a thread passes 100 turns; all three values are tunable
via `WINDOW_K`, `WINDOW_K_LARGE` and `LARGE_HISTORY_THRESHOLD` in `.env`.

The query router is history-aware: it returns both the route **and** a
rewritten, self-contained version of the question. That rewrite is what gets
embedded for retrieval, so a follow-up like *"and where did he study?"* — which
on its own contains nothing searchable — still finds the right chunks.

Tool calls are recorded as message metadata but never replayed as
`AIMessage.tool_calls` / `ToolMessage` pairs; a tool call replayed without its
result is rejected outright by the Groq API.

---

## 🛡️ License & Contributing

Built with modern async Python standards and open for developer customization. Feel free to extend routers, add new custom tools, or swap vector backends!
