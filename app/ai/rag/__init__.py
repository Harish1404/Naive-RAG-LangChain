"""
Retrieval-augmented generation, retrieval half only.

    data_processor.py  files on disk -> text -> deduplicated chunks
    embeddings.py      chunks -> vectors
    vector_store.py    vectors + keywords -> MongoDB Atlas, hybrid search with RRF
    pipeline.py        the two ends joined: ingest(folder) and retrieve(query)

Callers only ever need `pipeline.rag_pipeline`; the three modules under it are
implementation detail.
"""
