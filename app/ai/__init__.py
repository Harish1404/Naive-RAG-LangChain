"""
Everything the app knows about language models, retrieval and speech.

The layout is by concern, one folder each:

    chat/         one turn of a conversation, orchestrated by chat/service.py
    router/       decides which path a question takes, before any work is done
    rag/          ingestion and retrieval over MongoDB Atlas
    voice/        speech in (stt), speech out (tts), and the chunking between
    tools/        the callable tools, and the registry the tool loop resolves against
    mcp/          tools that belong to a user rather than to the app
    prompts/      the text handed to the models, kept out of the logic that sends it
    experimental/ written, not wired to any route

One rule holds this together: **the answering path does not touch the database.**
The caller loads history and hands it in; the answer comes back as a stream of
tokens. No node, no prompt, no router and no tool reads or writes Mongo.

Three modules break that, each on purpose, and a grep should never find a
fourth:

    chat/persistence.py    writes the finished answer back. Imported by
                           chat/service.py and by nothing else.
    rag/vector_store.py    the Atlas collection *is* the vector store, so the
                           storage is the feature rather than a dependency.
    mcp/client.py          a user's MCP tools cannot be built without that
                           user's stored credential, so this reads the
                           connectors collection. It is also why nothing here
                           may be cached across users — see the warning on the
                           cache in that file.
"""
