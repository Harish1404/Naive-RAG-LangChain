# RAG & Application Workflows

This document details the operational workflows of the system: **Document Ingestion** (indexing raw text into MongoDB Atlas) and **Query Routing & Execution** (answering user requests via dynamic routes).

---

## 1. Document Ingestion Workflow

Ingestion executes automatically on server startup via FastAPI's `lifespan` handler. It scans the `uploads/` folder, processes new or updated documents, and indexes them incrementally into MongoDB Atlas.

```mermaid
sequenceDiagram
    participant App as FastAPI App Lifespan
    participant DP as Data Processor
    participant VS as MongoDB Vector Store
    participant EM as Gemini Embeddings
    participant DB as MongoDB Atlas

    Note over App,DB: Server Boot & Automatic Ingestion Phase
    App->>VS: Fetch Existing Chunk IDs
    VS->>DB: Query Collection (_id, id)
    DB-->>VS: Return Existing ID Set
    App->>DP: Process Folder ("uploads/")
    DP->>DP: Load Files (.pdf, .txt, .md)
    DP->>DP: Recursive Character Splitter (1800 chars, 300 overlap)
    DP-->>App: Return Raw Chunks
    App->>App: Filter Out Already Ingested Chunks
    
    alt New Chunks Found
        App->>EM: Embed New Text Chunks
        EM-->>App: Return 768d Vector Embeddings
        App->>VS: Add New Chunks & Embeddings
        VS->>DB: Bulk Upsert Operations ($set)
        VS->>DB: Check & Create Atlas Vector & Keyword Indexes
    else No New Chunks
        App->>App: Skip Re-embedding (Zero API Cost)
    end
```

---

## 2. Dynamic Query Routing & Execution Workflow

When a user submits a query to the `/chatbot` endpoint, the system routes the request dynamically to optimize accuracy and resource usage.

```mermaid
sequenceDiagram
    actor User as Client / Frontend
    participant API as FastAPI /chatbot
    participant Router as Query Router
    participant Chat as Chat Service
    participant Tool as Weather Webhook Tool
    participant VS as MongoDB Hybrid Store
    participant LLM as Dual LLM Engine (Groq / Gemini)

    User->>API: POST /chatbot (model_type, user_prompt)
    API->>Chat: Initialize ChatService & Call chat()
    Chat->>Router: route(user_prompt)
    Router->>LLM: Classify Query (ROUTER_PROMPT)
    LLM-->>Router: Route ("RAG" | "TOOL" | "BOTH" | "DIRECT")

    alt Route: RAG
        Chat->>VS: Hybrid Search (VectorSearch + KeywordSearch + RRF)
        VS-->>Chat: Top-K Context Chunks
        Chat->>LLM: Stream Answer with Context
    else Route: TOOL
        Chat->>Tool: Execute get_weather(city)
        Tool-->>Chat: Webhook Result
        Chat->>LLM: Stream Answer with Tool Result
    else Route: BOTH
        Chat->>VS: Retrieve Context Chunks
        VS-->>Chat: Context Chunks (Entity / Location info)
        Chat->>Tool: Execute Tool with Discovered Context
        Tool-->>Chat: Webhook Result
        Chat->>LLM: Stream Combined Answer
    else Route: DIRECT
        Chat->>LLM: Stream Direct Parametric Response
    end

    LLM-->>User: Stream Response Tokens (StreamingResponse)
```
