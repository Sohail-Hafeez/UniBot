"""
backend/routes/voice.py

Voice endpoints: microphone transcription and spoken responses.

Backed by OpenAI (Whisper + TTS) specifically — see services/openai_voice.py
for why. Both routes require a signed-in user, same as chat/conversations:
once these make real (paid) OpenAI calls, they can't be left open to anyone
who finds the URL.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from services.firebase_auth import CurrentUser, get_current_user
from services.openai_voice import synthesize, transcribe

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/api/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Transcribe a recorded audio clip to text via Whisper."""

    audio_bytes = await file.read()

    if len(audio_bytes) < 1000:
        return {"text": ""}

    try:
        text = await transcribe(audio_bytes, file.filename)
    except Exception as e:
        logger.error("Transcription failed for user %s: %s", current_user.uid, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Transcription failed. Please try again.",
        ) from e

    return {"text": text}


class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"


@router.post("/api/tts")
async def text_to_speech(
    req: TTSRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Synthesise spoken audio for a piece of text via OpenAI TTS."""

    if not req.text.strip():
        return Response(content=b"", media_type="audio/mpeg")

    try:
        audio_bytes = await synthesize(req.text, req.voice)
    except Exception as e:
        logger.error("Speech synthesis failed for user %s: %s", current_user.uid, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Speech synthesis failed. Please try again.",
        ) from e

    return Response(content=audio_bytes, media_type="audio/mpeg")
