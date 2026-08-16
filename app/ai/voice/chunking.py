"""
Regrouping an LLM token stream into speakable chunks.

This sits between the model and the synthesiser and belongs to neither, which is
why it is its own module: it is pure text processing, with no network call and
no API key, and it is the piece most worth reading on its own.
"""

import re
from typing import AsyncIterator

# Sentence end followed by whitespace. The lookbehind keeps the punctuation
# attached to the sentence it belongs to, which matters because ElevenLabs uses
# it for prosody — stripping it makes the speech sound flat and run-on.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n+")

# Long enough that a clause carries some prosody, short enough that first audio
# is not held hostage by a model that forgot to punctuate.
_MAX_CHUNK_CHARS = 90

# Words whose trailing period is not a full stop. Without this, "Dr. Reddy"
# is flushed as two utterances and spoken with a pause in the middle of the
# name. A short explicit list beats a length heuristic, which cannot tell
# "Dr." from a genuinely short sentence like "Hello there."
_ABBREVIATIONS = {
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "vs", "etc",
    "inc", "ltd", "co", "no", "fig", "eg", "ie", "approx", "dept",
    "est", "vol", "ref", "pvt",
}

_LAST_WORD = re.compile(r"([A-Za-z]+)\.\s*$")


def _is_abbreviation(head: str) -> bool:
    """True if `head` ends on an abbreviation rather than a real sentence."""
    m = _LAST_WORD.search(head)
    return bool(m) and m.group(1).lower() in _ABBREVIATIONS


async def sentence_chunks(tokens: AsyncIterator[str]) -> AsyncIterator[str]:
    """Regroup an LLM token stream into speakable chunks.

    This is the single highest-leverage piece of the latency budget. Feeding
    ElevenLabs one token at a time produces choppy prosody; feeding it the whole
    answer means the first word is not spoken until the last one is generated.
    Flushing on sentence boundaries starts audio after the first sentence.
    """
    buf = ""
    async for token in tokens:
        buf += token
        # Flush every complete sentence sitting in the buffer, keeping the
        # trailing partial one behind for the next token.
        while True:
            match = _BOUNDARY.search(buf)
            if not match:
                break
            # "Dr. " is not the end of a sentence — keep it in the buffer and
            # look for the next boundary instead.
            while _is_abbreviation(buf[: match.end()]):
                later = _BOUNDARY.search(buf, match.end())
                if later is None:
                    match = None
                    break
                match = later
            if match is None:
                break
            head, buf = buf[: match.end()], buf[match.end() :]
            if head.strip():
                yield head

        # No punctuation in sight and the buffer is getting long — cut at the
        # last word break so a rambling answer still starts speaking.
        if len(buf) >= _MAX_CHUNK_CHARS:
            cut = buf.rfind(" ", 0, _MAX_CHUNK_CHARS)
            if cut <= 0:
                cut = _MAX_CHUNK_CHARS
            head, buf = buf[:cut], buf[cut:]
            if head.strip():
                yield head

    if buf.strip():
        yield buf
