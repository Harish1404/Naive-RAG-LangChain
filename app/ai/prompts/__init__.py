"""
The text handed to the models, kept apart from the code that sends it.

One module per consumer — `rag.py`, `router.py`, `voice.py`, `chain.py` — so a
prompt can be reworded without opening the logic that uses it, and so the diff of
a prompt change reads as a prompt change.
"""
