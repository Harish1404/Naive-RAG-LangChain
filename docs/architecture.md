# System Architecture

The following diagram outlines the high-level architecture of the RAG system and how data flows through the various components.

```mermaid
graph TD
    A[Raw Files <br/> PDF, TXT, MD] --> B(Data Processor)
    B -->|Text Chunks| C(RAG Pipeline)
    C --> D(Embedding Model <br/> SentenceTransformer)
    D -->|Embeddings| E[(Vector Store <br/> ChromaDB)]
    
    F[User Query] --> G(Chat Service)
    G --> C
    C -.-> D
    C -.-> E
    E -.->|Top K Chunks| G
    G --> H[LLM Generation]
    H --> I[Final Output]
```

### Component Details
- **Data Processor**: Parses raw files and chunks text.
- **RAG Pipeline**: Orchestrates ingestion and retrieval.
- **Embedding Model**: Runs a local `all-MiniLM-L6-v2` model to create vector representations.
- **Vector Store**: Uses ChromaDB to persist chunks and embeddings on disk.
- **Chat Service**: Interfaces with the LLM to generate grounded answers based on retrieved context.
