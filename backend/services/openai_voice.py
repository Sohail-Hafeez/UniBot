"""
backend/services/openai_voice.py

Speech-to-text and text-to-speech for the voice UI, backed by OpenAI.

Mistral (the rest of this app's LLM/embedding provider) has no audio
API, so voice features specifically use OpenAI's Whisper (transcription)
and TTS models. This is the only place in the backend that talks to
OpenAI — chat and retrieval are entirely unaffected and stay on Mistral.
"""

import io
import logging
import sys
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import OPENAI_API_KEY  # noqa: E402

logger = logging.getLogger(__name__)

TRANSCRIBE_MODEL = "whisper-1"
TTS_MODEL = "tts-1"

# Devanagari (Hindi script) unicode block. Hindi and Urdu share the same
# spoken phonetics, so Whisper sometimes transcribes Urdu speech into
# Devanagari instead of the expected Arabic script. If that happens,
# retry once forcing the Urdu language code.
_DEVANAGARI_RANGE = ("ऀ", "ॿ")

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Lazily-initialised async OpenAI client (shared singleton)."""

    global _client

    if _client is not None:
        return _client

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Voice features require an OpenAI key "
            "even though chat runs on Mistral."
        )

    _client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=30.0)

    logger.info("OpenAI voice client initialised.")

    return _client


def _looks_like_devanagari(text: str) -> bool:
    """True if more than half the alphabetic characters are Devanagari."""

    devanagari = sum(1 for c in text if _DEVANAGARI_RANGE[0] <= c <= _DEVANAGARI_RANGE[1])
    alpha = sum(1 for c in text if c.isalpha())

    return alpha > 0 and devanagari / alpha > 0.5


async def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """
    Transcribe recorded audio to text via Whisper.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio file content (e.g. a webm recording from the browser).
    filename : str
        Original filename — OpenAI uses its extension to infer format.

    Returns
    -------
    str
        The transcribed text (empty string if nothing was said).
    """

    client = _get_client()

    buf = io.BytesIO(audio_bytes)
    buf.name = filename or "audio.webm"

    result = await client.audio.transcriptions.create(model=TRANSCRIBE_MODEL, file=buf)
    text = (result.text or "").strip()

    if _looks_like_devanagari(text):
        logger.info("Transcript looked like Devanagari — retrying forced to Urdu.")
        buf2 = io.BytesIO(audio_bytes)
        buf2.name = filename or "audio.webm"
        retry = await client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL, file=buf2, language="ur"
        )
        text = (retry.text or "").strip()

    return text


async def synthesize(text: str, voice: str = "alloy") -> bytes:
    """
    Synthesise speech audio from text via OpenAI TTS.

    Parameters
    ----------
    text : str
        Text to speak.
    voice : str
        OpenAI TTS voice name (e.g. "alloy", "nova", "shimmer").

    Returns
    -------
    bytes
        MP3 audio content.
    """

    client = _get_client()

    response = await client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text,
        response_format="mp3",
    )

    return response.content
