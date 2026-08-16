"""
Text to speech: sentences in, PCM out, over the ElevenLabs WebSocket.

Also the on-disk cache for fixed phrases, and the monthly credit check — both
are about the same external account, so they live next to the client that spends
it.
"""

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
from pathlib import Path
from typing import AsyncIterator

import httpx
import websockets

from app.core.config import settings

logger = logging.getLogger(__name__)

# Written next to the app rather than in a temp dir so it survives a reload and
# is easy to inspect (and delete) while teaching. Gitignored.
#
# parents[3] is the project root from app/ai/voice/tts.py — count the folders,
# not the dots: voice -> ai -> app -> Langchain-RAG.
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".tts_cache"


def _cache_path(text: str, voice_id: str, model_id: str) -> Path:
    key = hashlib.sha256(f"{voice_id}|{model_id}|{text}".encode()).hexdigest()
    return _CACHE_DIR / f"{key}.pcm"


class ElevenLabsStream:
    """A single turn's worth of streaming TTS over the ElevenLabs WebSocket.

    Text goes in as the LLM produces it and audio comes back while the model is
    still writing — that overlap is what the REST endpoints cannot do, since
    they need the complete text up front.

    One instance per turn. Opening per turn rather than holding a long-lived
    socket also sidesteps the 20s inactivity timeout, which a user pausing to
    think would otherwise trip.
    """

    def __init__(self, voice_id: str | None = None, model_id: str | None = None):
        self.voice_id = voice_id or settings.eleven_voice_id
        self.model_id = model_id or settings.eleven_model_id
        self._ws = None
        self._spoken: list[str] = []

    @property
    def url(self) -> str:
        return (
            f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}"
            f"&output_format={settings.eleven_output_format}"
        )

    async def open(self) -> None:
        self._ws = await websockets.connect(
            self.url,
            additional_headers={"xi-api-key": settings.elevenlabs_api_key},
            max_size=None,
        )
        # ElevenLabs requires an initialising message before any text. A bare
        # space is the documented way to send settings without speaking a word.
        await self._ws.send(
            json.dumps(
                {
                    "text": " ",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
                }
            )
        )

    async def send_text(self, text: str) -> None:
        self._spoken.append(text)
        await self._ws.send(json.dumps({"text": text, "try_trigger_generation": True}))

    async def done_sending(self) -> None:
        """Signal end of input. An empty string is EOS in this protocol."""
        await self._ws.send(json.dumps({"text": ""}))

    async def audio(self) -> AsyncIterator[bytes]:
        """Yield decoded PCM as it arrives, until the server says isFinal."""
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                if msg.get("audio"):
                    # Audio arrives base64-encoded inside JSON, not as binary
                    # frames — so it has to be decoded before being forwarded.
                    yield base64.b64decode(msg["audio"])
                if msg.get("isFinal"):
                    break
        except websockets.exceptions.ConnectionClosed as e:
            # 1008 here is nearly always the free-tier library-voice rejection
            # or an invalid voice id; both are worth surfacing loudly.
            if e.code != 1000:
                logger.error(f"ElevenLabs closed the socket: {e.code} {e.reason}")
                raise

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    @property
    def spoken_text(self) -> str:
        return "".join(self._spoken)


async def stream_tts(
    chunks: AsyncIterator[str],
    on_audio,
    voice_id: str | None = None,
    stream: "ElevenLabsStream | None" = None,
    opening: asyncio.Task | None = None,
) -> None:
    """Push text chunks through ElevenLabs, handing each PCM buffer to `on_audio`.

    Sending and receiving run concurrently: waiting for the audio of sentence
    one before sending sentence two would serialise the very overlap that makes
    this fast.

    `stream`/`opening` let the caller start the ElevenLabs handshake early, in
    parallel with the router and the LLM. That connect costs a few hundred ms
    and is pure dead time if it only begins once the first sentence exists.
    """
    stream = stream or ElevenLabsStream(voice_id=voice_id)
    if opening is not None:
        await opening
    else:
        await stream.open()

    async def pump_text():
        try:
            async for chunk in chunks:
                await stream.send_text(chunk)
        finally:
            await stream.done_sending()

    sender = asyncio.create_task(pump_text())
    try:
        async for pcm in stream.audio():
            await on_audio(pcm)
        await sender
    finally:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
        await stream.close()


async def synth_cached(text: str, voice_id: str | None = None) -> bytes | None:
    """Whole-utterance TTS with an on-disk cache. Returns None on a miss.

    Only used for fixed phrases (greetings, error lines) and for replaying test
    utterances during development. Real answers go through `stream_tts`, since
    caching them would defeat the point of streaming.
    """
    if not settings.tts_cache_enabled:
        return None
    path = _cache_path(text, voice_id or settings.eleven_voice_id, settings.eleven_model_id)
    if path.exists():
        logger.info(f"TTS cache hit ({len(text)} chars, 0 credits): {text[:40]!r}")
        return path.read_bytes()
    return None


def cache_put(text: str, pcm: bytes, voice_id: str | None = None) -> None:
    if not settings.tts_cache_enabled or not pcm:
        return
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(text, voice_id or settings.eleven_voice_id, settings.eleven_model_id).write_bytes(pcm)


async def remaining_credits() -> int | None:
    """Credits left this month, or None if the key cannot read it.

    Needs the `user_read` scope. A key scoped to text-to-speech only still works
    fine for the pipeline, so a failure here is logged and shrugged off rather
    than raised — it is telemetry, not a dependency.
    """
    if not settings.elevenlabs_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": settings.elevenlabs_api_key},
            )
        if r.status_code != 200:
            logger.info(
                "ElevenLabs quota unavailable (%s) — key is missing the "
                "`user_read` scope. Regenerate it with that scope to enable "
                "credit logging.",
                r.status_code,
            )
            return None
        d = r.json()
        if not isinstance(d, dict):
            return None
        limit = d.get("character_limit")
        count = d.get("character_count")
        if isinstance(limit, (int, float)) and isinstance(count, (int, float)):
            return int(limit - count)
        return None
    except Exception as e:
        logger.warning(f"Could not read ElevenLabs quota: {e}")
        return None
