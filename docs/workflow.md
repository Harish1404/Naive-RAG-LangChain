# Application Workflows

> **How to read this document.** Each section is one workflow, told as a story from start
> to finish. §2 is the one to read first — it is a single chat turn, step by step. §3
> follows one conversation across several turns and is where memory becomes visible.

Four workflows:

| # | Workflow | When it runs |
|---|---|---|
| 1 | Document ingestion | Once, at server startup |
| 2 | A single chat turn | Every `POST /chatbot` |
| 3 | A conversation over time | Across many turns |
| 4 | Conversation management | New chat, sidebar, rename, delete |

---

## 1. Document Ingestion

Runs automatically on server boot via FastAPI's `lifespan` handler. It scans `uploads/`,
processes new documents, and indexes them into MongoDB Atlas.

The important property is that it is **incremental**: each chunk gets a deterministic id,
existing ids are fetched first, and only genuinely new chunks are embedded. Restarting the
server ten times costs one embedding run, not ten.

```mermaid
sequenceDiagram
    participant App as FastAPI Lifespan
    participant DP as Data Processor
    participant VS as Vector Store
    participant EM as Gemini Embeddings
    participant DB as MongoDB Atlas

    Note over App,DB: Startup order: LangSmith -> Mongo -> chat indexes -> ingestion

    App->>DB: connect + ping
    App->>DB: ensure chat indexes (conversations, messages)

    App->>VS: fetch existing chunk ids
    VS->>DB: query collection
    DB-->>VS: set of known ids

    App->>DP: process_folder("uploads/")
    DP->>DP: load .pdf / .txt / .md
    DP->>DP: split (1800 chars, 300 overlap)
    DP-->>App: raw chunks

    App->>App: drop chunks whose id already exists

    alt New chunks found
        App->>EM: embed new chunks
        EM-->>App: 768d vectors
        App->>VS: upsert chunks + vectors
        VS->>DB: bulk write
        VS->>DB: ensure vector_index + keyword_index
    else Nothing new
        App->>App: skip (zero API cost)
    end
```

---

## 2. A Single Chat Turn

This is the core workflow. A request arrives at `POST /chatbot`:

```json
{
  "conversation_id": "conv_9f8b2c1e-...",   // omit to start a new chat
  "user_prompt": "and where did he study?",
  "user_id": "default_user"                  // optional
}
```

### The eight steps

```mermaid
sequenceDiagram
    actor User
    participant API as POST /chatbot
    participant Store as Memory Store
    participant Win as Window Buffer
    participant Router as QueryRouter
    participant Chat as ChatService
    participant RAG as Hybrid Search
    participant Tool as Weather Tool
    participant LLM as Groq / Gemini

    User->>API: user_prompt (+ conversation_id?)

    rect rgb(240, 246, 255)
        Note over API,Store: 1-2. Resolve the thread, save the question
        alt conversation_id given
            API->>Store: load conversation
            Store-->>API: 404 if missing or deleted
        else no conversation_id
            API->>Store: create a new conversation
        end
        API->>Store: save user message (atomic seq)
    end

    rect rgb(243, 240, 255)
        Note over API,Win: 3. Load memory
        API->>Win: load(conversation_id)
        Win->>Store: last k*2+1 messages
        Win-->>API: last k turns as LangChain messages
    end

    rect rgb(255, 247, 237)
        Note over Chat,Router: 4. Route AND rewrite, in one call
        API->>Chat: ChatService(prompt, conversation_id, history)
        Chat->>Router: route(prompt, history)
        Router->>LLM: classify + resolve references
        LLM-->>Router: route + standalone_question
    end

    rect rgb(240, 253, 244)
        Note over Chat,LLM: 5-6. Do the work, stream the answer
        alt RAG
            Chat->>RAG: retrieve(standalone_question)
            RAG-->>Chat: top-k chunks
        else TOOL
            Chat->>Tool: get_weather(city)
            Tool-->>Chat: result
        else BOTH
            Chat->>RAG: retrieve(standalone_question)
            RAG-->>Chat: chunks (to find the city)
            Chat->>Tool: get_weather(city)
            Tool-->>Chat: result
        else DIRECT
            Note over Chat: no retrieval, no tools
        end
        Chat->>LLM: [system prompt] + [history] + [question]
        LLM-->>User: stream tokens
    end

    rect rgb(254, 242, 242)
        Note over Chat,Store: 7-8. Save the answer
        Chat->>Chat: collect tokens into a buffer
        Chat->>Store: save assistant message (+ route, partial flag)
    end
```

### Step by step

| # | Step | Detail |
|---|---|---|
| 1 | **Resolve the thread** | An id is shape-checked first (`422` if malformed), then loaded (`404` if missing or deleted). No id at all means a new conversation is created. |
| 2 | **Save the question** | Written *before* streaming, so it survives a crash and so errors surface as clean JSON. |
| 3 | **Load memory** | Last k turns, *excluding* the message just written — see the note below. |
| 4 | **Route + rewrite** | One model call returns both the route and a self-contained question. |
| 5 | **Retrieve / call tools** | Only the work the route requires. Retrieval uses the **rewritten** question. |
| 6 | **Stream** | `[system] + [history] + [question]` to the model; tokens go straight to the client. |
| 7 | **Collect** | Tokens are also appended to a buffer, since nothing else holds the finished answer. |
| 8 | **Save the answer** | With its route and a `partial` flag. |

> **Teaching note — the off-by-one in step 3.** The question is saved in step 2 and loaded
> back in step 3, so the newest stored message *is* the current question. `window.load()`
> drops that last message (`exclude_latest=True`), because the question is appended to the
> prompt explicitly at step 6. Without this the model would see it twice.

### What comes back

The body is a plain stream of text tokens. The thread id travels in a header:

```
X-Conversation-Id: conv_9f8b2c1e-4a77-4d1e-9c33-6b0f5d2a1e88
```

Read it on the first message of a new chat and send it back on every following message.

---

## 3. A Conversation Over Time

This is where memory earns its keep. Follow one real thread:

```mermaid
graph TB
    T1["<b>Turn 1</b><br/>User: Who is Harish?<br/>rewritten: Who is Harish?<br/>route: RAG<br/>history sent: 0 messages"]
    T2["<b>Turn 2</b><br/>User: what are his skills?<br/>rewritten: what are Harish Palanivel's skills?<br/>route: RAG<br/>history sent: 2 messages"]
    T3["<b>Turn 3</b><br/>User: is it raining in the city he lives in?<br/>rewritten: is it raining in the city Harish lives in?<br/>route: BOTH<br/>history sent: 4 messages"]
    T4["<b>Turn 4</b><br/>User: and tomorrow?<br/>rewritten: weather forecast in Chennai tomorrow?<br/>route: TOOL<br/>history sent: 6 messages"]
    T5["<b>Turn 5</b><br/>User: what did I ask you first?<br/>route: DIRECT<br/>Answer: You first asked me 'Who is Harish?'"]

    T1 --> T2 --> T3 --> T4 --> T5
```

Notice what each turn demonstrates:

- **Turn 2** — `"his"` is resolved to a name, so the search actually finds something.
- **Turn 3** — the route switches to `BOTH`: the city has to be looked up in the resume
  *before* the weather tool can be called.
- **Turn 4** — `"and tomorrow?"` contains no subject and no place. Only history makes it
  answerable, and the route switches back to `TOOL`.
- **Turn 5** — proof the model really is being shown the earlier messages.

### How the window slides

With `WINDOW_K = 4`, history grows to 8 messages and then stops:

| After turn | Messages stored | Messages replayed |
|---|---|---|
| 1 | 2 | 0 |
| 2 | 4 | 2 |
| 3 | 6 | 4 |
| 4 | 8 | 6 |
| 5 | 10 | 8 |
| 6 | 12 | **8** (capped) |
| 20 | 40 | **8** |

Past 100 turns the window widens to 5 turns (10 messages) via `WINDOW_K_LARGE`.

> **Teaching note — the trade-off.** A window is cheap and predictable, but it *forgets*.
> Ask about something from turn 2 while on turn 40 and the model will not know it. The
> standard next step is a **rolling summary**: as messages fall out of the window,
> summarise them into a `summary` field on the conversation and prepend it to the prompt.
> That keeps long threads coherent without unbounded token growth.

---

## 4. Conversation Management

The endpoints behind a chat sidebar.

```mermaid
graph LR
    NEW["POST /conversations<br/>New chat"] --> LIST
    LIST["GET /conversations<br/>Sidebar list"] --> OPEN["GET /conversations/{id}<br/>Open a thread"]
    OPEN --> SEND["POST /chatbot<br/>Continue it"]
    SEND --> LIST
    LIST --> REN["PATCH /conversations/{id}<br/>Rename"]
    LIST --> DEL["DELETE /conversations/{id}<br/>Soft delete"]
```

| Method | Path | Notes |
|---|---|---|
| `POST` | `/conversations` | Explicit new chat. Optional — posting to `/chatbot` without an id also creates one. |
| `GET` | `/conversations` | Sorted by `updated_at` descending. Supports `user_id`, `limit`, `skip`. |
| `GET` | `/conversations/{id}` | Full transcript, oldest first. Page backwards with `before_seq`. |
| `PATCH` | `/conversations/{id}` | Rename. |
| `DELETE` | `/conversations/{id}` | Soft delete — hidden from the sidebar, messages kept on disk. |

**Titles** are derived automatically from the first user message (trimmed to 60 characters),
so a thread names itself. A title supplied at creation, or set later via `PATCH`, is never
overwritten.

---

## 5. Trying it yourself

```bash
python server.py

# 1. Start a chat — the id comes back in the header
curl -N -D - -X POST http://127.0.0.1:8000/chatbot \
  -H 'Content-Type: application/json' \
  -d '{"user_prompt": "Who is Harish?"}'

# 2. Continue it — note the follow-up has no name in it
curl -N -X POST http://127.0.0.1:8000/chatbot \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id": "conv_...", "user_prompt": "and where did he study?"}'

# 3. Read the thread back
curl http://127.0.0.1:8000/conversations/conv_...

# 4. See every thread
curl http://127.0.0.1:8000/conversations
```

Watch the server log while doing this — it prints the two lines that explain each turn:

```
Memory window for conv_...: 2 message(s) (k=4 turns, thread has ~1 turn(s))
Router selected: RAG for query: 'and where did he study?' (searching for: 'Where did Harish study?')
```

The first shows how much memory was replayed; the second shows the rewritten question that
was actually searched for. Between them they explain almost every surprising answer.
