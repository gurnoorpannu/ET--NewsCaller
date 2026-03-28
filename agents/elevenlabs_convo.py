"""
agents/elevenlabs_convo.py — ElevenLabs Conversational AI voice Q&A handler.

Alternative to Gemini Live (agents/gemini_live.py).

Uses ElevenLabs' pre-configured "Tony" agent to answer questions about the
news briefing. Unlike Gemini Live (audio-in / audio-out), this path sends
the question as text and receives Tony's voice back as audio.

Architecture:
    ElevenLabs SDK (sync Conversation class) runs in an isolated thread.
    A custom AudioInterface feeds text messages instead of microphone audio,
    and captures the 16kHz PCM response chunks for later MP3 conversion.

Audio flow:
    Question text → ElevenLabs Tony (WebSocket) → raw PCM 16kHz → pydub → MP3

Advantages over Gemini Live:
    - No ffmpeg required (no audio input conversion)
    - Works for both voice input (STT text) and direct text questions
    - Tony is a pre-configured persona with its own personality

Fallback:
    If the SDK is missing, agent ID is wrong, or the session fails,
    app.py falls back to answer_question() + text_to_speech() automatically.
"""

import io
import threading
from typing import Callable, Optional

from agents.conversation import build_context
from config import ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID
from models.schemas import Briefing, UserProfile


# ---------------------------------------------------------------------------
# Custom AudioInterface — text-question in, PCM audio out
# ---------------------------------------------------------------------------

class _TextInputAudioInterface:
    """
    Custom AudioInterface that sends a text question to Tony and
    collects PCM audio response chunks.

    The ElevenLabs SDK's AudioInterface contract:
        start(input_callback)  → called when WebSocket is ready; call
                                  input_callback(pcm_bytes) to stream mic audio.
                                  We spawn a thread to send text instead.
        stop()                 → session ended; clean up resources.
        output(audio: bytes)   → SDK calls this with 16kHz PCM chunks from Tony.
        interrupt()            → Tony was interrupted; discard buffered audio.

    Input format:  text message (no microphone audio sent)
    Output format: 16-bit PCM, 16kHz, mono (ElevenLabs Conversational AI default)
    """

    # Recommended input chunk size per ElevenLabs SDK defaults (250ms @ 16kHz)
    _CHUNK_BYTES = 8000  # 4000 samples × 2 bytes/sample = 8000 bytes

    def __init__(self, question: str, context: str):
        """
        Args:
            question: The user's question text (from STT or direct typing).
            context:  Briefing context string (articles + user profile).
        """
        self._question = question
        self._context = context
        self._output_chunks: list[bytes] = []
        self._stopped = threading.Event()
        # Injected after Conversation object is created — see set_conversation()
        self._conversation = None

    def set_conversation(self, conversation) -> None:
        """
        Inject a reference to the Conversation object so we can call
        send_contextual_update() and send_user_message() from the
        background sender thread.
        """
        self._conversation = conversation

    def start(self, input_callback: Callable[[bytes], None]) -> None:
        """
        Called by the SDK once the WebSocket is open and the initiation
        message has been sent. We don't stream microphone audio — instead
        we spawn a thread that sends the briefing context + question text.

        The 0.5s initial sleep gives the server time to process the
        conversation_initiation_metadata exchange before we send updates.
        """
        def _send_messages() -> None:
            import time

            # Give the server time to respond to conversation_initiation_client_data
            time.sleep(0.5)
            if self._stopped.is_set() or self._conversation is None:
                return

            # Step 1: Seed briefing context as a non-interrupting update.
            # Tony uses this as background knowledge without triggering a response.
            try:
                self._conversation.send_contextual_update(self._context)
            except Exception as e:
                print(f"[ElevenLabsConvo] contextual_update failed: {e}")

            # Small gap between context injection and the actual question
            time.sleep(0.15)
            if self._stopped.is_set():
                return

            # Step 2: Send the user's question as a text user_message.
            # Tony will process and respond with voice audio.
            try:
                self._conversation.send_user_message(self._question)
            except Exception as e:
                print(f"[ElevenLabsConvo] send_user_message failed: {e}")

        threading.Thread(target=_send_messages, daemon=True, name="EL-Sender").start()

    def stop(self) -> None:
        """Called when the session ends. Signals the sender thread to abort."""
        self._stopped.set()

    def output(self, audio: bytes) -> None:
        """
        SDK calls this with raw 16kHz PCM chunks as Tony speaks.
        We buffer them all; they're assembled into an MP3 after the session.
        """
        self._output_chunks.append(audio)

    def interrupt(self) -> None:
        """
        For single-turn Q&A, interruptions are a no-op.
        In a streaming use case, we'd clear _output_chunks here.
        """
        pass

    def get_output_pcm(self) -> bytes:
        """Return all received PCM chunks concatenated into a single bytes object."""
        return b"".join(self._output_chunks)


# ---------------------------------------------------------------------------
# PCM → MP3/WAV conversion
# ---------------------------------------------------------------------------

def _pcm_to_mp3(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """
    Convert raw PCM (ElevenLabs output: 16kHz, 16-bit, mono) → MP3.

    Uses pydub + ffmpeg. Falls back to WAV wrapping if pydub is unavailable.
    Both formats are accepted by Streamlit's st.audio().

    ElevenLabs Conversational AI outputs 16kHz PCM (vs Gemini Live's 24kHz).
    """
    try:
        from pydub import AudioSegment

        segment = AudioSegment(
            data=pcm_bytes,
            sample_width=2,          # 16-bit = 2 bytes per sample
            frame_rate=sample_rate,  # 16000 Hz
            channels=1,              # mono
        )
        mp3_buffer = io.BytesIO()
        segment.export(mp3_buffer, format="mp3")
        mp3_buffer.seek(0)
        return mp3_buffer.read()

    except Exception as e:
        print(f"[ElevenLabsConvo] pydub PCM→MP3 failed: {e}. Returning WAV fallback.")
        return _pcm_to_wav(pcm_bytes, sample_rate)


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw PCM in a WAV header. Used when pydub/ffmpeg is unavailable."""
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)           # 16-bit = 2 bytes
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# Public API — called from app.py
# ---------------------------------------------------------------------------

def elevenlabs_convo_answer(
    question: str,
    briefing: Briefing,
    profile: UserProfile,
    chat_history: list[dict] = None,
) -> tuple[bytes, str]:
    """
    Voice Q&A via ElevenLabs Conversational AI (Agent Tony).

    Takes the user's question as text, returns (mp3_bytes, transcript_text).

    Unlike Gemini Live, no audio input is required — we send text and
    receive Tony's spoken response as 16kHz PCM, converted to MP3.

    Works for both:
        - Voice input: STT already transcribed the question to text
        - Text input:  User typed the question directly

    Args:
        question:     User's question text (from STT or direct typing).
        briefing:     Briefing object produced by the pipeline.
        profile:      UserProfile for this session.
        chat_history: Prior Q&A turns as list of {'role': str, 'content': str}.
                      Pass the snapshot BEFORE appending the current question.

    Returns:
        (mp3_bytes, transcript):
            mp3_bytes  → pass to st.audio(..., format='audio/mp3')
            transcript → display in chat history (may be empty string)

    Raises:
        RuntimeError: SDK not installed, session timeout, or empty audio response.
    """
    # --- Config guard ---
    if not ELEVENLABS_AGENT_ID:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not set in .env")

    # --- Import guard ---
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs.conversational_ai.conversation import Conversation
    except ImportError as e:
        raise RuntimeError(f"elevenlabs SDK not installed. Run: pip install elevenlabs. ({e})")

    # --- Build briefing context string ---
    # Reuses build_context() from conversation.py — same format as Gemini Live.
    context = build_context(briefing, profile)
    if chat_history:
        history_lines = []
        for msg in chat_history[-6:]:  # Last 6 turns to stay within context budget
            role = "User" if msg["role"] == "user" else "MyET AI"
            history_lines.append(f"{role}: {msg['content']}")
        if history_lines:
            context += "\n\nPrevious conversation:\n" + "\n".join(history_lines)

    # --- Setup ---
    audio_interface = _TextInputAudioInterface(question=question, context=context)
    response_text: list[str] = []
    result: dict = {}
    error_container: dict = {}

    # ElevenLabs client — Tony is requires_auth=False (public agent),
    # but we pass the key if available for higher rate limits.
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY or "public")

    def _on_agent_response(text: str) -> None:
        """
        Called by the SDK when Tony finishes his spoken response.
        Captures the text transcript and schedules session end after a
        brief delay to allow any trailing PCM chunks to arrive.
        """
        response_text.append(text)
        # Wait 1.5s after text response before ending — audio chunks may still be in-flight
        threading.Timer(1.5, conversation.end_session).start()

    conversation = Conversation(
        client=client,
        agent_id=ELEVENLABS_AGENT_ID,
        requires_auth=False,  # Tony is publicly accessible
        audio_interface=audio_interface,
        callback_agent_response=_on_agent_response,
    )

    # Inject conversation reference so the interface can call send_user_message()
    audio_interface.set_conversation(conversation)

    def _thread_target() -> None:
        """
        Run the ElevenLabs session in an isolated thread.
        Same pattern as gemini_live.py — avoids any asyncio/Streamlit conflicts.
        """
        try:
            conversation.start_session()
            # Blocks until end_session() is called (from _on_agent_response timer)
            conversation.wait_for_session_end()
            result["pcm"] = audio_interface.get_output_pcm()
            result["text"] = " ".join(response_text)
        except Exception as e:
            error_container["error"] = e

    # Run in isolated thread with a 30s ceiling (same as Gemini Live)
    thread = threading.Thread(target=_thread_target, daemon=True, name="EL-Session")
    thread.start()
    thread.join(timeout=30)

    if thread.is_alive():
        conversation.end_session()
        raise RuntimeError("ElevenLabs session timed out after 30 seconds.")

    if "error" in error_container:
        raise error_container["error"]

    if not result.get("pcm"):
        raise RuntimeError(
            "ElevenLabs returned empty audio. "
            "Verify ELEVENLABS_AGENT_ID and agent status at elevenlabs.io."
        )

    # Convert Tony's 16kHz PCM response → MP3 for st.audio()
    mp3_bytes = _pcm_to_mp3(result["pcm"], sample_rate=16000)
    return mp3_bytes, result.get("text", "")
