# Chunking Strategy

To efficiently retrieve relevant information and fit context within the LLM's context window limits, documents are split into smaller chunks.

### Strategy Details
- **Chunk Size**: 300 words
- **Overlap**: 50 words
- **Reasoning**: A 50-word overlap prevents sentences or specific semantic context from being abruptly cut in half across two chunks.

```mermaid
graph TD
    subgraph Original Document
        T[Continuous Text Stream]
    end
    
    subgraph Overlapping Chunks
        C1[Chunk 1 <br/> Words 1 to 300]
        C2[Chunk 2 <br/> Words 251 to 550]
        C3[Chunk 3 <br/> Words 501 to 800]
    end
    
    T --> C1
    T --> C2
    T --> C3
    
    C1 -.->|50 Word Overlap| C2
    C2 -.->|50 Word Overlap| C3
    
    style C1 fill:#f9f,stroke:#333,stroke-width:2px
    style C2 fill:#bbf,stroke:#333,stroke-width:2px
    style C3 fill:#dfd,stroke:#333,stroke-width:2px
```
