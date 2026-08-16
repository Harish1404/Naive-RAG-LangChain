"""
The tools a model may call, and the registry it resolves them through.

`registry.py` is the single list. Binding, dispatch and the "unknown tool"
warning all read from it, so adding a second tool means writing the module and
appending one entry — no edit to the tool loop.
"""
