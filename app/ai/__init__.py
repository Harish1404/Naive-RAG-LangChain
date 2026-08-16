"""
Everything the app knows about language models, retrieval and speech.

The layout is by concern, one folder each:

    chat/         one turn of a conversation, orchestrated by chat/service.py
    router/       decides which path a question takes, before any work is done
    rag/          ingestion and retrieval over MongoDB Atlas
    voice/        speech in (stt), speech out (tts), and the chunking between
    tools/        the callable tools, and the registry the tool loop resolves against
    prompts/      the text handed to the models, kept out of the logic that sends it
    experimental/ written, not wired to any route

One rule holds this together: **nothing under app/ai/ imports the database.** The
caller loads history and hands it in; the answer comes back as a stream of tokens.
The single deliberate exception is chat/persistence.py, which exists to write a
finished answer back and is imported by chat/service.py alone.
"""
