"""
agents/elevenlabs_tts.py — ElevenLabs Text-to-Speech for Q&A responses.

How this fits the pipeline:
    User question
        ↓
    agents/conversation.py  (Gemini LLM — knows the briefing, gives correct answer)
        ↓  answer text
    elevenlabs_tts.py       (ElevenLabs TTS — converts answer text → MP3 audio)
        ↓  mp3 bytes
    st.audio()              (Streamlit plays it)

Why NOT ElevenLabs Conversational AI (Tony):
    Tony is a pre-configured standalone agent with his own system prompt.
    He doesn't know our news briefing, so he always greets with
    "Hello! How can I help you today?" instead of answering.
    Using Gemini for intelligence + ElevenLabs for voice solves this cleanly.

ElevenLabs TTS API used here:
    POST /v1/text-to-speech/{voice_id}
    Returns raw MP3 bytes directly — no WebSocket, no threading needed.
"""

import io
from config import ELEVENLABS_API_KEY

# ---------------------------------------------------------------------------
# Default voice — "Rachel" is a clear, neutral female voice available on
# all ElevenLabs tiers. Override by setting ELEVENLABS_VOICE_ID in .env.
# ---------------------------------------------------------------------------
import os
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel


def text_to_speech_elevenlabs(text: str) -> bytes:
    """
    Convert answer text to MP3 audio using ElevenLabs TTS API.

    This is a simple REST call — no WebSocket, no threading, no PCM conversion.
    Returns raw MP3 bytes ready for st.audio(..., format='audio/mp3').

    Args:
        text: The answer text from Gemini (already conversational, no markdown).

    Returns:
        MP3 bytes from ElevenLabs.

    Raises:
        RuntimeError: If the API key is missing, the request fails, or
                      the elevenlabs SDK is not installed.
    """
    # Guard: API key must be set
    if not ELEVENLABS_API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set in .env. "
            "Add it to use ElevenLabs TTS voice."
        )

    # Import guard — elevenlabs SDK is optional
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        raise RuntimeError(
            "elevenlabs SDK not installed. Run: pip install elevenlabs"
        )

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    # Call TTS API — returns a generator of audio chunks
    # model_id "eleven_turbo_v2" is the fastest/cheapest model for real-time use
    audio_stream = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=text,
        model_id="eleven_turbo_v2",
        output_format="mp3_44100_128",
    )

    # Collect all chunks into a single bytes object
    mp3_bytes = b"".join(audio_stream)
    return mp3_bytes
