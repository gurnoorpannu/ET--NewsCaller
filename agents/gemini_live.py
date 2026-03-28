"""
agents/gemini_live.py — Gemini Live real-time voice Q&A handler.

Replaces the three-step turn-based chain for the Q&A phase:
    speech_to_text() → answer_question() → text_to_speech()

With a single Gemini Live WebSocket session that handles audio input,
reasoning, and audio output in one round-trip.

Architecture:
    Gemini Live requires async/await (WebSocket-based).
    Streamlit is synchronous. We bridge this by running the entire
    async session inside a threading.Thread with its own event loop
    via asyncio.run() — the standard pattern for Streamlit + asyncio.

Audio flow:
    Browser WebM → ffmpeg → raw PCM 16kHz  (Gemini input format)
    Gemini output → raw PCM 24kHz → pydub → MP3  (Streamlit st.audio format)

Fallback:
    If ffmpeg is missing, GEMINI_API_KEY is unset, or Gemini Live fails,
    app.py falls back to answer_question() + text_to_speech() automatically.
"""

import asyncio
import io
import os
import subprocess
import threading
from typing import Optional

from google import genai
from google.genai import types

from agents.conversation import build_context  # reuse existing context builder
from config import GEMINI_API_KEY
from models.schemas import Briefing, UserProfile


# Gemini Live model — supports native bidirectional audio I/O
_LIVE_MODEL = "gemini-2.0-flash-live-001"


# ---------------------------------------------------------------------------
# Audio format conversion helpers
# ---------------------------------------------------------------------------

def _webm_to_pcm(webm_bytes: bytes) -> Optional[bytes]:
    """
    Convert browser WebM audio to raw PCM for Gemini Live input.

    Gemini Live input requirements:
        - Format: raw signed 16-bit PCM (no WAV/MP3 container)
        - Sample rate: 16,000 Hz
        - Channels: mono (1)
        - Endianness: little-endian
        - MIME type when sending: audio/pcm;rate=16000

    Uses ffmpeg via subprocess with list args (no shell — no injection risk).
    Returns None if ffmpeg is not installed.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(webm_bytes)
        webm_path = f.name

    # Output: raw PCM bytes (no container)
    pcm_path = webm_path.replace(".webm", ".pcm")

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", webm_path,
                "-f", "s16le",    # signed 16-bit little-endian PCM
                "-ar", "16000",   # 16 kHz — Gemini Live input rate
                "-ac", "1",       # mono
                pcm_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 or not os.path.exists(pcm_path):
            return None

        with open(pcm_path, "rb") as f:
            return f.read()

    except (subprocess.TimeoutExpired, FileNotFoundError):
        # FileNotFoundError = ffmpeg not installed
        return None
    finally:
        for path in [webm_path, pcm_path]:
            try:
                os.unlink(path)
            except OSError:
                pass


def _pcm_to_mp3(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """
    Convert raw PCM (Gemini Live output) to MP3 for st.audio().

    Gemini Live output:
        - Raw signed 16-bit PCM, 24 kHz, mono (no container)

    st.audio() needs a proper container (MP3 or WAV).

    Uses pydub + ffmpeg. Falls back to a WAV wrapper if pydub is unavailable.
    Both MP3 and WAV are accepted by st.audio().
    """
    try:
        from pydub import AudioSegment

        # Tell pydub the exact raw format so it wraps it correctly
        segment = AudioSegment(
            data=pcm_bytes,
            sample_width=2,         # 16-bit = 2 bytes per sample
            frame_rate=sample_rate,  # 24000 Hz (Gemini Live output rate)
            channels=1,             # mono
        )
        mp3_buffer = io.BytesIO()
        segment.export(mp3_buffer, format="mp3")
        mp3_buffer.seek(0)
        return mp3_buffer.read()

    except Exception as e:
        print(f"[GeminiLive] pydub PCM→MP3 failed: {e}. Returning WAV fallback.")
        return _pcm_to_wav(pcm_bytes, sample_rate)


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """
    Wrap raw PCM in a WAV header — used as fallback when pydub/ffmpeg unavailable.
    st.audio() accepts WAV with format='audio/wav'.
    """
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)            # 16-bit = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# Core async Gemini Live session
# ---------------------------------------------------------------------------

async def _run_live_session(
    user_audio_pcm: bytes,
    system_prompt: str,
    briefing_context: str,
) -> tuple[bytes, str]:
    """
    Open a Gemini Live WebSocket session, seed context, send audio, collect response.

    This is an async coroutine — it MUST be called via asyncio.run() inside a
    threading.Thread. Never call it directly from Streamlit (no event loop there).

    Flow:
        1. Open session with system_instruction (persona) in config
        2. Seed briefing context as fake conversation history (no response triggered)
        3. Send user's audio as raw PCM
        4. Signal end-of-turn
        5. Collect audio chunks + transcript until turn_complete

    Returns:
        (response_audio_pcm, response_transcript)
        response_audio_pcm: raw PCM 24kHz — pass to _pcm_to_mp3()
        response_transcript: text of Gemini's spoken response (may be empty string)
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Session-level configuration:
    # - response_modalities=["AUDIO"] → Gemini returns audio chunks (not text)
    # - system_instruction → persona injected once at session start
    # - speech_config → which preset voice Gemini uses for output
    # - output_audio_transcription → also return text of what Gemini says
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            role="user",  # Gemini Live expects system_instruction with role="user"
            parts=[types.Part(text=system_prompt)],
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Kore"  # Clear, professional voice
                    # Other options: Aoede, Charon, Fenrir, Puck
                )
            )
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    audio_chunks: list[bytes] = []
    transcript_parts: list[str] = []

    async with client.aio.live.connect(model=_LIVE_MODEL, config=config) as session:

        # Step 1: Seed briefing context as fake prior conversation.
        # turn_complete=False means "I'm still setting up — don't respond yet."
        # This puts full article context into Gemini's context window without
        # triggering audio generation or consuming audio output quota.
        await session.send_client_content(
            turns=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"Today's news briefing:\n\n{briefing_context}")],
                ),
                types.Content(
                    role="model",
                    parts=[types.Part(
                        text="Understood. I have your full briefing loaded and I'm ready "
                             "to answer questions about today's stories."
                    )],
                ),
            ],
            turn_complete=False,  # prime context, don't respond
        )

        # Step 2: Send user's audio question as raw PCM 16kHz
        await session.send_realtime_input(
            audio=types.Blob(
                data=user_audio_pcm,
                mime_type="audio/pcm;rate=16000",
            )
        )

        # Step 3: Signal end-of-turn so Gemini knows the user is done speaking
        await session.send_realtime_input(end_of_turn=True)

        # Step 4: Collect audio response chunks until Gemini signals turn_complete
        async for response in session.receive():
            # Top-level audio data (streamed in real-time chunks)
            if response.data:
                audio_chunks.append(response.data)

            # Structured content (audio parts + transcription)
            if response.server_content:
                if response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_chunks.append(part.inline_data.data)

                # Text transcript of what Gemini is saying aloud (for chat display)
                if response.server_content.output_transcription:
                    text = response.server_content.output_transcription.text
                    if text:
                        transcript_parts.append(text)

                # turn_complete = Gemini finished its response
                if response.server_content.turn_complete:
                    break

    return b"".join(audio_chunks), " ".join(transcript_parts).strip()


# ---------------------------------------------------------------------------
# Public API — called from app.py
# ---------------------------------------------------------------------------

def gemini_live_answer(
    user_audio_webm: bytes,
    briefing: Briefing,
    profile: UserProfile,
    chat_history: list[dict] = None,
) -> tuple[bytes, str]:
    """
    Voice Q&A via Gemini Live — public entry point called from app.py.

    Takes browser WebM audio bytes, returns (mp3_bytes, transcript_text).

    The entire async Gemini Live session runs in an isolated threading.Thread
    with its own asyncio event loop — this avoids any conflict with Streamlit's
    synchronous execution model.

    Args:
        user_audio_webm: Raw WebM bytes from audio_recorder_streamlit.
        briefing:        Briefing object produced by the pipeline.
        profile:         UserProfile for this session.
        chat_history:    Prior Q&A turns as list of {'role': str, 'content': str}.
                         Pass the snapshot BEFORE the current question is appended.

    Returns:
        (mp3_bytes, transcript):
            mp3_bytes  → pass to st.audio(..., format='audio/mp3')
            transcript → display in chat history (may be empty string)

    Raises:
        RuntimeError: GEMINI_API_KEY missing, ffmpeg not installed,
                      30s timeout, or empty audio response from Gemini.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        raise RuntimeError("GEMINI_API_KEY is not configured in .env")

    # Convert browser WebM → raw PCM 16kHz (Gemini Live input format)
    user_audio_pcm = _webm_to_pcm(user_audio_webm)
    if user_audio_pcm is None:
        raise RuntimeError(
            "ffmpeg is required for Gemini Live voice input. "
            "Install with: brew install ffmpeg  (macOS) or  apt install ffmpeg  (Linux)"
        )

    # system_instruction: short persona injected at session level (persists whole session)
    system_prompt = (
        f"You are MyET AI, a personal news companion for {profile.name} "
        f"({profile.role}). Answer questions about their news briefing. "
        f"Be conversational and concise (2-4 sentences). "
        f"No markdown, no bullet points — your response will be spoken aloud. "
        f"If a question is outside the briefing scope, say so briefly."
    )

    # briefing_context: full article context seeded as fake conversation history.
    # Reuses build_context() from conversation.py — same format, no duplication.
    briefing_context = build_context(briefing, profile)

    # Append recent chat history so Gemini knows what was already discussed
    if chat_history:
        history_lines = []
        for msg in chat_history[-6:]:  # last 6 turns to stay within context budget
            role = "User" if msg["role"] == "user" else "MyET AI"
            history_lines.append(f"{role}: {msg['content']}")
        if history_lines:
            briefing_context += "\n\nPrevious conversation:\n" + "\n".join(history_lines)

    # Run the async Gemini Live session in an isolated thread.
    # asyncio.run() inside threading.Thread creates a fresh event loop,
    # completely independent from Streamlit's runtime — no conflicts.
    result: dict = {}
    error_container: dict = {}

    def _thread_target():
        try:
            pcm, text = asyncio.run(
                _run_live_session(user_audio_pcm, system_prompt, briefing_context)
            )
            result["pcm"] = pcm
            result["text"] = text
        except Exception as e:
            error_container["error"] = e

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    thread.join(timeout=30)  # 30s ceiling — Live is fast but quota stalls happen

    if thread.is_alive():
        raise RuntimeError("Gemini Live session timed out after 30 seconds.")

    if "error" in error_container:
        raise error_container["error"]

    if not result.get("pcm"):
        raise RuntimeError("Gemini Live returned empty audio response.")

    # Convert Gemini's raw PCM output (24kHz) → MP3 for st.audio()
    mp3_bytes = _pcm_to_mp3(result["pcm"], sample_rate=24000)
    return mp3_bytes, result.get("text", "")
