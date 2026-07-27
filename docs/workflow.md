# RAG Workflows

The application workflow is divided into two distinct phases: **Ingestion** (processing files) and **Retrieval** (answering questions).

## 1. Ingestion Workflow

This process happens when documents are uploaded or indexed by the system.

```mermaid
sequenceDiagram
    participant Docs as Raw Documents
    participant DP as Data Processor
    participant EM as Embedding Model
    participant VS as Vector Store
    
    Note over Docs,VS: Document Ingestion Phase
    Docs->>DP: Load Text & PDF Files
    DP->>DP: Split Text into Chunks
    DP->>EM: Send Text Chunks
    EM->>EM: Generate Embeddings (MiniLM-L6-v2)
    EM->>VS: Store Chunks, Vectors, and Metadata
```

## 2. Retrieval & Generation Workflow

This process happens when a user asks a question.

```mermaid
sequenceDiagram
    actor User as User
    participant Chat as Chat Service
    participant RAG as RAG Pipeline
    participant EM as Embedding Model
    participant VS as Vector Store
    participant LLM as Language Model
    
    Note over User,LLM: Query & Generation Phase
    User->>Chat: Ask Question
    Chat->>RAG: Request Context for Query
    RAG->>EM: Embed Query Text
    EM-->>RAG: Query Embedding Vector
    RAG->>VS: Search Vector Store
    VS-->>RAG: Return Top-K Relevant Chunks
    RAG-->>Chat: Return Context String
    Chat->>LLM: Send System Prompt + Context + Question
    LLM-->>Chat: Generate Grounded Answer
    Chat-->>User: Final Output
```
