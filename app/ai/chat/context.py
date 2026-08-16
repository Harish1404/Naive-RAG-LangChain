"""
Everything one turn knows about itself.

This replaces the pile of attributes that used to accumulate on ChatService.
The point of pulling it out is that a node now receives a value it can read
rather than a service it could call back into — the four nodes cannot reach the
router, the persistence layer, or each other through it.
"""

from dataclasses import dataclass, field

from langchain_core.messages import BaseMessage, SystemMessage

from app.ai.chat.models import DEFAULT_MAX_TOKENS
from app.ai.prompts.voice import VOICE_SYSTEM_PROMPT
from app.core.config import settings


@dataclass
class TurnContext:
    """One user message, and what the pipeline works out about it.

    The first four fields come from the caller. The rest are filled in by
    ChatService once the router has run, and read by whichever node handles the
    turn.
    """

    user_prompt: str
    conversation_id: str
    history: list[BaseMessage] = field(default_factory=list)
    voice_mode: bool = False

    # Set by ChatService after routing.
    route: str | None = None

    # What retrieval actually searches for: the question with its
    # back-references resolved. Falls back to the raw prompt.
    search_query: str = ""

    # Tool activity, recorded for the stored message's metadata.
    tool_calls: list[dict] = field(default_factory=list)

    # Derived in __post_init__ from voice_mode.
    max_tokens: int = DEFAULT_MAX_TOKENS

    def __post_init__(self) -> None:
        # A copy, never the caller's list: nodes append to the message list they
        # build, and history is replayed as-is on every turn.
        self.history = list(self.history or [])

        # Voice answers are spoken, so they need different shaping than text
        # ones: a few sentences, no markdown, numbers written how they sound.
        # Injecting it at the head of the history rather than editing each of
        # the four nodes means it applies to RAG, TOOL, BOTH and DIRECT alike,
        # and lands directly after that node's own system prompt. The cap is
        # also a cost control — on the ElevenLabs free tier a 2000-character
        # reply is a tenth of the month's credits.
        if self.voice_mode:
            self.history.insert(0, SystemMessage(content=VOICE_SYSTEM_PROMPT))
            self.max_tokens = settings.voice_max_tokens

        if not self.search_query:
            self.search_query = self.user_prompt
