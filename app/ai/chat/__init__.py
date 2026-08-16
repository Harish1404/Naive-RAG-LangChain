"""
One turn of a conversation, from a question to a stream of answer tokens.

    service.py      the orchestrator — route, pick a node, stream, persist
    context.py      TurnContext: everything one turn knows about itself
    models.py       building the chat models, and warming them up
    nodes/          the four answer paths, one file each
    tool_loop.py    the hand-written tool-call round-trip, used by TOOL and BOTH
    streaming.py    chunks -> plain text tokens
    persistence.py  writing the finished answer back to MongoDB

Callers want `service.ChatService` and nothing else.

Reading order, if this is new to you: context.py to see what a turn is, then
service.py to see the shape of one, then whichever node you care about.
"""
