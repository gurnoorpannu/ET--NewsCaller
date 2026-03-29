"""
agents/elevenlabs_convo.py — ElevenLabs Conversational AI voice Q&A handler.

How it works:
    We use the ElevenLabs Conversation SDK but inject the news briefing context
    as a per-session system prompt override via ConversationInitiationData.
    This means Tony answers based on TODAY'S actual news, not his generic persona.

    Flow:
        Question text
            ↓
        ElevenLabs Conversation (Tony agent + briefing system prompt injected)
            ↓  spoken PCM audio + transcript text
        PCM → MP3
            ↓
        st.audio()

    The key fix vs the old approach:
        Old: send_contextual_update() — Tony ignores it, greets with "Hello!"
        New: conversation_config_override["agent"]["prompt"]["prompt"] = briefing_system_prompt
             Tony now STARTS the session already knowing the news.

Audio flow:
    Question text → WebSocket → Tony (briefing-aware) → raw PCM 16kHz → pydub → MP3

Fallback:
    If SDK is missing, agent ID is wrong, or the session fails,
    app.py falls back to answer_question() + gTTS automatically.
"""

import io
import threading
from typing import Callable, Optional

from agents.conversation import build_context
from config import ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID
from models.schemas import Briefing, UserProfile


# ---------------------------------------------------------------------------
# Build system prompt for Tony — tells him about the briefing upfront
# ---------------------------------------------------------------------------

def _build_system_prompt(briefing: Briefing, profile: UserProfile, chat_history: list[dict]) -> str:
    """
    Build a system prompt that injects the full briefing context into Tony's
    session via conversation_config_override. Tony will start the session
    already knowing the news instead of greeting with "Hello!".

    The prompt is injected as the agent's prompt override, so Tony treats
    this as his core instructions for the entire session.
    """
    context = build_context(briefing, profile)

    history_text = ""
    if chat_history:
        lines = []
        for msg in chat_history[-6:]:
            role = "User" if msg["role"] == "user" else "MyET AI"
            lines.append(f"{role}: {msg['content']}")
        if lines:
            history_text = "\n\nPrevious conversation:\n" + "\n".join(lines)

    return f"""You are MyET AI, a personal news companion for {profile.name} ({profile.role}).
You just delivered a personalized news briefing. The user now has follow-up questions.

Answer ONLY based on the briefing below. Be conversational, concise (2-4 sentences),
and speak naturally — your response will be read aloud.
Do NOT use markdown, bullet points, or special characters.
Do NOT introduce yourself or say hello — just answer the question directly.
If asked something outside the briefing, briefly note that and answer what you can.

{context}{history_text}

When the user asks a question, answer it immediately and directly."""


# ---------------------------------------------------------------------------
# Custom AudioInterface — text-question in, PCM audio out
# ---------------------------------------------------------------------------

class _TextInputAudioInterface:
    """
    Custom AudioInterface that sends a text question to Tony and
    collects PCM audio response chunks.

    ElevenLabs AudioInterface contract:
        start(input_callback)  → WebSocket is open; spawn thread to send user message.
        stop()                 → session ended.
        output(audio: bytes)   → SDK calls this with 16kHz PCM chunks.
        interrupt()            → Tony interrupted; for single-turn Q&A this is a no-op.

    We no longer use send_contextual_update() because it's unreliable.
    The briefing context is already baked into Tony's prompt via config override.
    We just send the user's question text.
    """

    def __init__(self, question: str):
        self._question = question
        self._output_chunks: list[bytes] = []
        self._stopped = threading.Event()
        self._conversation = None  # Injected after Conversation object is created

    def set_conversation(self, conversation) -> None:
        """Inject the Conversation object so we can call send_user_message()."""
        self._conversation = conversation

    def start(self, input_callback: Callable[[bytes], None]) -> None:
        """
        Spawn a background thread to send the question once the session is ready.
        0.5s sleep gives Tony time to finish his opening handshake before we speak.
        """
        def _send() -> None:
            import time
            time.sleep(0.5)
            if self._stopped.is_set() or self._conversation is None:
                return
            try:
                # Send the user's question directly — Tony already knows the news
                # because we injected it as his system prompt.
                self._conversation.send_user_message(self._question)
            except Exception as e:
                print(f"[ElevenLabsConvo] send_user_message failed: {e}")

        threading.Thread(target=_send, daemon=True, name="EL-Sender").start()

    def stop(self) -> None:
        self._stopped.set()

    def output(self, audio: bytes) -> None:
        """Buffer 16kHz PCM chunks from Tony's spoken response."""
        self._output_chunks.append(audio)

    def interrupt(self) -> None:
        """No-op for single-turn Q&A."""
        pass

    def get_output_pcm(self) -> bytes:
        return b"".join(self._output_chunks)


# ---------------------------------------------------------------------------
# PCM → MP3 / WAV conversion
# ---------------------------------------------------------------------------

def _pcm_to_mp3(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """
    Convert raw PCM (ElevenLabs: 16kHz, 16-bit, mono) → MP3.
    Falls back to WAV if pydub/ffmpeg is unavailable.
    Both formats work with st.audio().
    """
    try:
        from pydub import AudioSegment
        segment = AudioSegment(
            data=pcm_bytes,
            sample_width=2,          # 16-bit = 2 bytes per sample
            frame_rate=sample_rate,
            channels=1,              # mono
        )
        buf = io.BytesIO()
        segment.export(buf, format="mp3")
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"[ElevenLabsConvo] pydub PCM→MP3 failed: {e}. Falling back to WAV.")
        return _pcm_to_wav(pcm_bytes, sample_rate)


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw PCM in a WAV header. Used when pydub/ffmpeg is unavailable."""
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf.read()


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
    Voice Q&A via ElevenLabs Conversational AI.

    Injects the full news briefing as Tony's system prompt via
    conversation_config_override so he answers about the actual news
    instead of greeting generically.

    Args:
        question:     User's question (from STT or typed).
        briefing:     Briefing produced by the pipeline.
        profile:      UserProfile for this session.
        chat_history: Prior Q&A turns (snapshot before current question).

    Returns:
        (mp3_bytes, transcript_text)

    Raises:
        RuntimeError: SDK missing, no agent ID, session timeout, or empty audio.
    """
    # Guard: agent ID must be set
    if not ELEVENLABS_AGENT_ID:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not set in .env")

    # Import guard
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs.conversational_ai.conversation import (
            Conversation,
            ConversationInitiationData,
        )
    except ImportError as e:
        raise RuntimeError(f"elevenlabs SDK not installed. Run: pip install elevenlabs. ({e})")

    # Build a per-session system prompt with the full briefing context.
    # conversation_config_override replaces Tony's default agent prompt for this
    # session only — Tony will start knowing the news and answer correctly.
    system_prompt = _build_system_prompt(briefing, profile, chat_history or [])
    session_config = ConversationInitiationData(
        conversation_config_override={
            "agent": {
                "prompt": {
                    "prompt": system_prompt
                },
                # Keep Tony's first_message empty so he doesn't greet — just listens
                "first_message": "",
            }
        }
    )

    audio_interface = _TextInputAudioInterface(question=question)
    response_text: list[str] = []
    result: dict = {}
    error_container: dict = {}

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY or "public")

    def _on_agent_response(text: str) -> None:
        """
        Called when Tony finishes speaking. Captures transcript and
        schedules session end after 1.5s to let trailing PCM chunks arrive.
        """
        response_text.append(text)
        threading.Timer(1.5, conversation.end_session).start()

    conversation = Conversation(
        client=client,
        agent_id=ELEVENLABS_AGENT_ID,
        requires_auth=False,
        audio_interface=audio_interface,
        config=session_config,                    # ← briefing injected here
        callback_agent_response=_on_agent_response,
    )

    audio_interface.set_conversation(conversation)

    def _thread_target() -> None:
        """Run ElevenLabs session in an isolated thread to avoid asyncio conflicts."""
        try:
            conversation.start_session()
            conversation.wait_for_session_end()
            result["pcm"]  = audio_interface.get_output_pcm()
            result["text"] = " ".join(response_text)
        except Exception as e:
            error_container["error"] = e

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
            "Check ELEVENLABS_AGENT_ID and agent status at elevenlabs.io."
        )

    mp3_bytes = _pcm_to_mp3(result["pcm"], sample_rate=16000)
    return mp3_bytes, result.get("text", "")
