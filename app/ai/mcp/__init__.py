"""
MCP: tools that belong to a *user*, not to the app.

`app/ai/tools/` holds the tools everyone shares — the weather webhook is the
same webhook whoever asks. The tools here are different in kind: they reach into
one person's GitHub account, using one person's credential, and two users asking
the same question must get different answers.

    config.py   which MCP servers exist, and which of their tools we bind
    client.py   resolving a user id to that user's live tools, with a cache

That per-user distinction is the one thing to keep in mind when changing
anything here. A tool object carries its owner's bearer token inside the
connection headers it was built from, so anything that caches, shares or
defaults a tool list is a way for one user to act as another. See the warnings
on the cache in client.py.
"""
