# RAG Codebase Analysis Report

This document provides a comprehensive overview of the Retrieval-Augmented Generation (RAG) implementation within this repository. 

## Documentation & Visual Diagrams
- [System Architecture](docs/architecture.md)
- [RAG Workflows](docs/workflow.md)
- [Chunking Strategy](docs/chunking.md)

## 1. Core Architecture

The RAG system is built in Python and adopts a modular architecture to separate data ingestion, embedding generation, vector storage, and orchestration.

### Key Components:
- **`data_processor.py`**: Handles reading raw text from various file formats (currently `.txt`, `.md`, and `.pdf` via `pypdf`) and splits the text into manageable chunks.
- **`embeddings.py`**: Wraps the `sentence_transformers` library. It uses the `all-MiniLM-L6-v2` model by default to generate dense vector representations (embeddings). This runs locally on the CPU, meaning no external API calls are required for embeddings.
- **`vector_store.py`**: Manages the vector database using **ChromaDB**. It uses a persistent client saving data to disk (`./chroma_db`), allowing embeddings and chunks to survive restarts. 
- **`rag_pipeline.py`**: Acts as the orchestrator. It provides two main operations: `ingest` (processing a folder of documents into the vector store) and `retrieve` (fetching relevant chunks for a user query).
- **LLM Integration (ChatService)**: The `rag_pipeline.py` is purely for retrieval. It connects to the `ChatService` (located in the `ai` module), which handles passing the retrieved context to the actual Large Language Model for generation.

## 2. Workflow

The application workflow is divided into two distinct phases: Ingestion and Retrieval.

### Ingestion Workflow
1. **Document Loading**: Reads all supported files from a target folder.
2. **Chunking**: Splits the raw text of each document into smaller, overlapping chunks (see Chunk Strategy below).
3. **Embedding**: Passes the chunks through the local `SentenceTransformer` model to generate vector embeddings.
4. **Storage**: Saves the chunk IDs, the raw text chunks, their embeddings, and metadata (like the source filename) into the ChromaDB collection. *(Note: Currently, the pipeline wipes and resets the collection on fresh ingestion).*

### Retrieval Workflow
1. **User Query**: A user submits a question.
2. **Query Embedding**: The question is embedded using the exact same local model used during ingestion.
3. **Vector Search**: The system queries ChromaDB to find the top `k` (default is 4) chunks with embeddings most similar to the query embedding.
4. **Context Construction**: The retrieved chunks are formatted along with their source metadata into a prompt.
5. **Generation**: The compiled prompt is sent to the LLM to generate the final response.

## 3. Chunk Strategy and Workflows

The chunking strategy is vital for maintaining context while fitting within LLM context window limits.

- **Method**: Fixed-size word chunking with overlap.
- **Parameters**: 
  - **Chunk Size**: `300` words.
  - **Overlap**: `50` words.
- **Rationale**: The text is split by words. An overlap of 50 words is intentionally used between consecutive chunks so that sentence meanings or critical contexts are not abruptly cut in half at chunk boundaries.
- **Metadata Association**: Each chunk is given a unique ID (e.g., `filename.pdf-0`) and retains its source filename in its metadata, allowing the system to cite where information came from.

## 4. About Our Prompt

The prompts used to instruct the LLM are stored in `app/prompts/rag_prompt.py`. 

- **System Prompt (`RAG_SYSTEM_PROMPT`)**: This prompt strictly constrains the LLM's behavior. 
  - It forces the LLM to act as an assistant that uses **ONLY** the provided context.
  - It includes an explicit instruction to state *"I don't know based on the information I have."* if the answer cannot be found in the context (preventing hallucinations).
  - It asks the LLM to keep answers concise and to cite the source file when useful.
- **Context Builder (`build_context_message`)**: This function formats the retrieved chunks before they are sent to the LLM. It injects the source name in brackets (e.g., `[my_resume.pdf]`) followed by the raw chunk text, ending with the user's specific question. This layout allows the LLM to easily associate facts with their origin documents.

## 5. Other Key Objectives & Takeaways

- **Privacy & Cost-Efficiency**: By using `sentence-transformers` locally, the application does not leak document data to external embedding APIs and saves on API costs during the ingestion phase.
- **Traceability**: Because metadata (source document name) is stored with every chunk and passed into the prompt, the LLM can provide transparent answers with citations.
- **Extensibility**: The separation of `VectorStore`, `EmbeddingModel`, and `RAGPipeline` means it is straightforward to swap out ChromaDB for another vector database (like Qdrant or Pinecone) or swap the embedding model without having to rewrite the core logic.
