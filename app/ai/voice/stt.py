"""
Speech to text: one whole utterance of microphone PCM in, a transcript out.

Groq's Whisper endpoint does the work. The only real complication is the
container — see pcm_to_wav.
"""

import asyncio
import logging
import wave
from io import BytesIO

from groq import AsyncGroq

from app.core.config import settings

logger = logging.getLogger(__name__)

STT_MODEL = "whisper-large-v3-turbo"

_groq_client: AsyncGroq | None = None


def _groq() -> AsyncGroq:
    """One client for the process, created on first use.

    Deliberately lazy: building it at import time binds it to whichever event
    loop happens to be current, which under uvicorn --reload is not the loop
    that ends up serving requests.
    """
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(api_key=settings.groq_api_key)
    return _groq_client


def pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM16 mono in a 44-byte WAV header.

    Groq needs a container it can sniff; it will not take headerless PCM. The
    stdlib `wave` module writes one with no third-party dependency at all, which
    is the whole reason this pipeline needs neither ffmpeg nor pydub.
    """
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def transcribe_pcm(pcm: bytes, sample_rate: int | None = None) -> str:
    """Transcribe one whole utterance of raw PCM16 mono.

    Returns the transcript VERBATIM. The previous version of this file ran the
    transcript through Gemini with a "summarize short and crisp" prompt and
    returned the summary, which silently destroyed the user's actual words.
    """
    sample_rate = sample_rate or settings.mic_sample_rate
    wav = pcm_to_wav(pcm, sample_rate)

    resp = await _groq().audio.transcriptions.create(
        # The filename is not cosmetic — Groq picks the decoder off the
        # extension, so a wrong one is rejected even when the bytes are valid.
        file=("utterance.wav", wav, "audio/wav"),
        model=STT_MODEL,
        response_format="text",
    )
    # response_format="text" yields a bare string; the SDK still wraps it in an
    # object for some versions, so both shapes are accepted.
    text = resp if isinstance(resp, str) else getattr(resp, "text", "")
    return text.strip()


async def warm_up() -> None:
    """Pay the TLS/connection cost at startup instead of on the first turn.

    Measured on this machine: the first Groq transcription takes ~1000ms and
    every one after it ~230ms. That second number is the real cost of the
    model; the first is connection setup. Without this the first student to
    press the mic button gets a visibly worse experience than everyone after.

    Sends 100ms of silence — Whisper returns empty, which is fine and free.
    """
    try:
        t = asyncio.get_event_loop().time()
        await transcribe_pcm(b"\x00\x00" * (settings.mic_sample_rate // 10))
        logger.info(
            f"Groq STT warmed up in {(asyncio.get_event_loop().time() - t) * 1000:.0f}ms"
        )
    except Exception as e:
        # Never block startup on this — it is an optimisation, not a dependency.
        logger.warning(f"STT warm-up skipped: {e}")
