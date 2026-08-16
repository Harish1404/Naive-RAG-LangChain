"""
The classifier that runs before any work is done.

`query_router.py` answers two questions in one model call: which path should
handle this turn (RAG / TOOL / BOTH / DIRECT), and what the question looks like
with its back-references resolved. The second answer is what retrieval actually
searches for.

Not to be confused with `app/routes/`, which is HTTP.
"""
