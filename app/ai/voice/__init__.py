"""
The audio ends of the voice pipeline: speech in, speech out.

    stt.py       microphone PCM -> text, via Groq Whisper
    chunking.py  a stream of LLM tokens -> speakable sentences
    tts.py       those sentences -> PCM, via the ElevenLabs WebSocket

Everything here works on raw PCM16 little-endian mono, because that is what the
browser can produce without an encoder and consume without a decoder. Keeping
the wire format decoder-free on both ends is what removes ffmpeg, pydub and
MediaSource from the design — the bytes are inspectable at every hop.

Nothing in this package knows about FastAPI or about the LLM; app/routes/voice.py
is what wires the three halves together.
"""
