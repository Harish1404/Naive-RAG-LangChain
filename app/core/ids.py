"""
Identifier generation for conversations and messages.

Ids are UUID4 strings with a short type prefix, stored in MongoDB as plain
`str` rather than BSON UUID/Binary. Keeping them as strings means the same
value travels unchanged from Mongo -> Python -> JSON -> the URL bar, with no
codec options on the Motor client and no encoding surprises.

The prefix is not decoration: it makes a mistyped or mismatched id fail fast
(a message id pasted into a conversation route is rejected before it ever
reaches the database) and makes ids self-describing in logs and traces.
"""

from uuid import UUID, uuid4

CONVERSATION_PREFIX = "conv"
MESSAGE_PREFIX = "msg"


def new_conversation_id() -> str:
    return f"{CONVERSATION_PREFIX}_{uuid4()}"


def new_message_id() -> str:
    return f"{MESSAGE_PREFIX}_{uuid4()}"


def is_valid_id(value: str, prefix: str) -> bool:
    """
    True when `value` is a well-formed id of the given type.

    Used by the route layer to reject junk with a 422 before a database call
    is made, so a malformed id can never be mistaken for "not found".
    """
    if not isinstance(value, str):
        return False

    head, _, tail = value.partition("_")
    if head != prefix or not tail:
        return False

    try:
        UUID(tail)
    except ValueError:
        return False

    return True


def is_conversation_id(value: str) -> bool:
    return is_valid_id(value, CONVERSATION_PREFIX)
