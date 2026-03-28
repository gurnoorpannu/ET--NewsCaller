# Bug Fixes + Gemini Live Q&A Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical/medium bugs in the 7-agent news pipeline and replace the turn-based voice Q&A with Gemini Live for lower-latency bidirectional audio.

**Architecture:** Bug fixes are applied in-place to existing files with minimal diffs. Gemini Live is added as a new `agents/gemini_live.py` module that's wired into `app.py` as the primary Q&A path with automatic fallback to the existing `answer_question()` + `text_to_speech()` chain.

**Tech Stack:** Python 3.11+, Streamlit, Pydantic v2, google-genai SDK (Gemini Live), pydub (PCM→MP3), requests, subprocess (ffmpeg), html (XSS escaping)

---

## Chunk 1: Critical Security & Logic Bugs

### Task 1: Fix `_call_gemini` retry loop + move API key to header

**Files:**
- Modify: `utils/llm.py`

- [ ] **Step 1: Read the current file**

```bash
cat utils/llm.py
```

- [ ] **Step 2: Replace `_call_gemini` with corrected version**

Replace the entire `_call_gemini` function (lines 11–32) with:

```python
def _call_gemini(prompt: str, temperature: float = 0.7) -> str:
    """
    Call Gemini REST API with retry on 429 rate-limit errors.

    Key sent via 'x-goog-api-key' header (not URL param) to keep it
    out of server logs and Python tracebacks.

    Retries up to 4 times with exponential back-off on 429.
    Raises RuntimeError after all attempts are exhausted.
    """
    # API key in header — never in the URL where it leaks into logs
    url = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent"
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    last_response = None
    for attempt in range(4):  # attempts 0-3 (4 total)
        resp = requests.post(url, json=payload, headers=headers, timeout=30)

        if resp.status_code == 429:
            # Back-off: 10s, 20s, 30s, 40s
            wait = 10 * (attempt + 1)
            print(f"[LLM] Rate limited. Waiting {wait}s (attempt {attempt + 1}/4)...")
            time.sleep(wait)
            last_response = resp
            continue  # retry

        # For any non-429 error, raise immediately (400, 500, etc.)
        resp.raise_for_status()

        # Success — parse and return
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    # All 4 attempts were rate-limited
    raise RuntimeError(
        f"Gemini API rate limit exhausted after 4 attempts. "
        f"Last HTTP status: {last_response.status_code if last_response else 'unknown'}"
    )
```

- [ ] **Step 3: Verify the file looks correct**

```bash
cat utils/llm.py
```

Expected: `_call_gemini` uses `headers={"x-goog-api-key": ...}`, no `?key=` in URL, raises `RuntimeError` after loop.

- [ ] **Step 4: Commit**

```bash
git add utils/llm.py
git commit -m "fix: move Gemini API key to header, fix retry loop post-loop dead code"
```

---

### Task 2: Fix shell injection in `_webm_to_wav_ffmpeg`

**Files:**
- Modify: `agents/voice.py`

- [ ] **Step 1: Add subprocess import and replace `_webm_to_wav_ffmpeg`**

At the top of `agents/voice.py`, ensure `import subprocess` is present (add after `import os` if missing).

Replace the `_webm_to_wav_ffmpeg` function (lines 37–40):

```python
def _webm_to_wav_ffmpeg(webm_path: str, wav_path: str) -> bool:
    """
    Convert WebM to WAV using ffmpeg via subprocess (no shell — no injection risk).
    Returns True if conversion succeeded and output file exists.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", webm_path,
                "-ar", "16000",   # 16 kHz sample rate for speech recognition
                "-ac", "1",       # mono channel
                wav_path,
            ],
            capture_output=True,  # suppress stdout/stderr noise
            timeout=30,           # don't hang forever
        )
        return result.returncode == 0 and os.path.exists(wav_path)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # FileNotFoundError = ffmpeg not installed
        return False
```

- [ ] **Step 2: Verify**

```bash
cat agents/voice.py | head -50
```

Expected: `subprocess.run([...])` with a list of args, no `os.system`.

- [ ] **Step 3: Commit**

```bash
git add agents/voice.py
git commit -m "fix: replace os.system ffmpeg call with subprocess.run to eliminate shell injection"
```

---

### Task 3: Add `isinstance` guard to `ask_llm_json`

**Files:**
- Modify: `utils/llm.py`

- [ ] **Step 1: Replace `ask_llm_json` body**

Replace the `ask_llm_json` function (lines 49–54):

```python
def ask_llm_json(prompt: str, temperature: float = 0.3) -> dict | list:
    """
    Send a prompt expecting JSON back. Returns parsed Python dict or list.

    Raises ValueError if Gemini returns valid JSON that isn't a dict or list
    (e.g. a bare string or number), since all callers expect a structured object.
    """
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
    raw = _call_gemini(full_prompt, temperature).strip()
    raw = _strip_markdown_fences(raw)
    result = json.loads(raw)

    # Guard: all callers expect a dict or list, not a scalar
    if not isinstance(result, (dict, list)):
        raise ValueError(
            f"Gemini returned valid JSON but not a dict/list: {type(result).__name__!r} — raw: {raw[:100]}"
        )
    return result
```

- [ ] **Step 2: Commit**

```bash
git add utils/llm.py
git commit -m "fix: validate ask_llm_json returns dict/list, not scalar JSON"
```

---

## Chunk 2: Medium Bugs — App Logic & Security

### Task 4: Wire `run_pipeline()` in loading page + add double-run guard

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Remove inline agent imports from `render_loading_page`**

In `render_loading_page()` (around lines 132–184), replace the entire try block that manually calls agents with a single `run_pipeline()` call:

```python
def render_loading_page():
    """Step 2: Run pipeline with progress."""
    st.markdown("<h1 class='main-header'>🎙️ MyET AI</h1>", unsafe_allow_html=True)

    profile = st.session_state.profile

    # Guard: prevent double-execution if Streamlit re-runs this page
    # while the pipeline is already running (e.g., heartbeat ping)
    if st.session_state.get("pipeline_running"):
        st.info(f"Preparing your personalized briefing, {profile.name}...")
        st.spinner("Pipeline is running...")
        return

    st.session_state.pipeline_running = True
    st.info(f"Preparing your personalized briefing, {profile.name}...")
    progress = st.progress(0, text="Starting pipeline...")

    try:
        # run_pipeline() handles all 5 agents with rate-limit gaps between calls
        # (defined in pipeline.py — _CALL_GAP = 6s between LLM calls)
        progress.progress(10, text="📡 Fetching news articles...")

        from pipeline import run_pipeline
        briefing = run_pipeline(profile)

        progress.progress(95, text="🎙️ Preparing voice...")
        from agents.voice import text_to_speech
        audio_bytes = text_to_speech(briefing.summary_text)

        st.session_state.briefing = briefing
        st.session_state.briefing_audio = audio_bytes
        progress.progress(100, text="✅ Done!")

        st.session_state.pipeline_running = False
        st.session_state.step = "briefing"
        st.rerun()

    except Exception as e:
        st.session_state.pipeline_running = False
        st.error(f"Pipeline error: {e}")
        if st.button("← Go Back"):
            st.session_state.step = "profile"
            st.rerun()
```

- [ ] **Step 2: Add `pipeline_running` to `init_session_state` defaults**

In `init_session_state()` (lines 51–63), add `"pipeline_running": False` to the defaults dict:

```python
defaults = {
    "step": "profile",
    "profile": None,
    "briefing": None,
    "chat_history": [],
    "briefing_audio": None,
    "last_response_audio": None,
    "pipeline_running": False,   # guard against double pipeline execution
    "last_audio_hash": None,     # for audio dedup (Task 6)
}
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: use run_pipeline() in loading page to restore rate-limit gaps, add double-run guard"
```

---

### Task 5: Fix XSS — HTML-escape dynamic content in article cards

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add `import html` at the top of `app.py`**

After the existing imports at the top:

```python
import html as html_lib  # for escaping user/RSS content in unsafe_allow_html blocks
```

- [ ] **Step 2: Update the article card rendering loop**

In `render_briefing_page()`, replace the `st.markdown(f"""...""")` block inside the `for i, article in enumerate(...)` loop:

```python
    for i, article in enumerate(briefing.top_articles, 1):
        score = article.relevance_score
        if score >= 0.7:
            badge_class = "high-relevance"
            badge_text = f"Relevance: {score:.0%}"
        elif score >= 0.4:
            badge_class = "med-relevance"
            badge_text = f"Relevance: {score:.0%}"
        else:
            badge_class = "low-relevance"
            badge_text = f"Relevance: {score:.0%}"

        # Escape all dynamic values before injecting into HTML
        # (RSS titles/descriptions can contain <script> or HTML entities)
        title_safe = html_lib.escape(article.title)
        source_safe = html_lib.escape(article.source)
        desc_safe = html_lib.escape(article.description[:200])
        why_safe = html_lib.escape(article.why_it_matters)
        topics_safe = html_lib.escape(", ".join(article.topics))
        sentiment_safe = html_lib.escape(article.sentiment)

        st.markdown(f"""
        <div class='article-card'>
            <h4>{i}. {title_safe}</h4>
            <span class='relevance-badge {badge_class}'>{badge_text}</span>
            &nbsp;&nbsp;<span style='color:#b2bec3;'>{source_safe}</span>
            <p style='margin-top:0.5rem;'>{desc_safe}</p>
            <p style='color:#6c5ce7; font-style:italic;'>💡 {why_safe}</p>
            <small>Topics: {topics_safe} | Sentiment: {sentiment_safe}</small>
        </div>
        """, unsafe_allow_html=True)
```

- [ ] **Step 3: Also escape chat messages rendered with unsafe_allow_html**

In `render_briefing_page()`, replace the chat history rendering loop:

```python
    for msg in st.session_state.chat_history:
        content_safe = html_lib.escape(msg["content"])
        if msg["role"] == "user":
            st.markdown(f"<div class='chat-msg user-msg'>🗣️ <b>You:</b> {content_safe}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-msg ai-msg'>🤖 <b>MyET AI:</b> {content_safe}</div>", unsafe_allow_html=True)
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "fix: html-escape all RSS/LLM content injected into unsafe_allow_html blocks"
```

---

### Task 6: Fix duplicate question in chat history + audio dedup

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Fix `process_user_question` — pass history without current message**

In `process_user_question()` (lines 301–332), the user message is appended to `chat_history` BEFORE being passed to `answer_question`, causing it to appear twice in the LLM prompt. Fix by passing history snapshot before appending:

```python
def process_user_question(question: str):
    """Process a user question and generate AI response."""
    briefing = st.session_state.briefing
    profile = st.session_state.profile

    # Snapshot history BEFORE adding current question
    # (answer_question adds "User's question: {question}" separately)
    history_snapshot = list(st.session_state.chat_history)

    # Now add the user message to visible chat history
    st.session_state.chat_history.append({"role": "user", "content": question})

    try:
        response = answer_question(
            question=question,
            briefing=briefing,
            profile=profile,
            chat_history=history_snapshot,  # history WITHOUT current question
        )
    except Exception as e:
        response = f"Sorry, I couldn't process that right now. ({e})"
        print(f"[Q&A] Error: {e}")

    st.session_state.chat_history.append({"role": "assistant", "content": response})

    try:
        from agents.voice import text_to_speech
        audio = text_to_speech(response)
        st.session_state.last_response_audio = audio
    except Exception as e:
        print(f"[Voice] TTS error for Q&A response: {e}")
        st.session_state.last_response_audio = None

    st.rerun()
```

- [ ] **Step 2: Fix audio dedup — skip re-processing same audio bytes**

In `render_briefing_page()`, in the voice input section, add a hash check before calling `process_user_question`:

```python
    with col_voice:
        try:
            from audio_recorder_streamlit import audio_recorder
            import hashlib

            audio_bytes = audio_recorder(
                text="🎤 Tap to speak",
                recording_color="#6c5ce7",
                neutral_color="#b2bec3",
                pause_threshold=2.0,
            )
            if audio_bytes:
                # Deduplicate: skip if this is the same audio as last time
                # (audio_recorder returns the same bytes on every Streamlit rerun
                #  until new audio is recorded)
                audio_hash = hashlib.md5(audio_bytes).hexdigest()
                if audio_hash != st.session_state.get("last_audio_hash"):
                    st.session_state.last_audio_hash = audio_hash
                    with st.spinner("Transcribing..."):
                        from agents.voice import speech_to_text
                        user_text = speech_to_text(audio_bytes)
                    if user_text:
                        st.success(f"Heard: {user_text}")
                        process_user_question(user_text)
                    else:
                        st.warning("⚠️ Couldn't transcribe audio. Type your question below instead.")
        except ImportError:
            st.info("Voice input requires audio-recorder-streamlit package.")
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "fix: pass pre-question history snapshot to LLM, add audio hash dedup"
```

---

## Chunk 3: Gemini Live Integration

### Task 7: Create `agents/gemini_live.py`

**Files:**
- Create: `agents/gemini_live.py`

- [ ] **Step 1: Create the file**

```python
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
    via asyncio.run() — this is the standard pattern for Streamlit + asyncio.

Audio flow:
    Browser WebM → ffmpeg → raw PCM 16kHz (Gemini input)
    Gemini output → raw PCM 24kHz → pydub → MP3 (Streamlit st.audio)

Fallback:
    If ffmpeg is missing, GEMINI_API_KEY is unset, or Gemini Live fails,
    the caller (app.py) falls back to answer_question() + text_to_speech().
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
    Convert browser WebM audio to raw PCM suitable for Gemini Live input.

    Gemini Live requires:
        - Format: raw signed 16-bit PCM (no WAV/MP3 container)
        - Sample rate: 16,000 Hz
        - Channels: mono (1)
        - Endianness: little-endian

    Uses ffmpeg via subprocess (list args — no shell, no injection risk).
    Returns None if ffmpeg is not installed.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(webm_bytes)
        webm_path = f.name

    # Raw PCM output file (no container — just bytes)
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

    Gemini Live outputs:
        - Raw signed 16-bit PCM, 24 kHz, mono

    st.audio() needs:
        - MP3 or WAV with a proper container header

    Uses pydub + ffmpeg. Falls back to a WAV wrapper if pydub is unavailable
    (WAV is also accepted by st.audio with format='audio/wav').
    """
    try:
        from pydub import AudioSegment

        # Tell pydub the raw format so it can wrap it correctly
        segment = AudioSegment(
            data=pcm_bytes,
            sample_width=2,        # 16-bit = 2 bytes per sample
            frame_rate=sample_rate, # 24000 Hz (Gemini Live output rate)
            channels=1,            # mono
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
    Wrap raw PCM in a WAV header.
    Used as fallback when pydub/ffmpeg is unavailable.
    """
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
# Core async Gemini Live session
# ---------------------------------------------------------------------------

async def _run_live_session(
    user_audio_pcm: bytes,
    system_prompt: str,
    briefing_context: str,
) -> tuple[bytes, str]:
    """
    Open a Gemini Live WebSocket session, seed context, send audio, collect response.

    This is an async function — it must be called via asyncio.run() in a thread.
    Never call this directly from Streamlit (no running event loop there).

    Args:
        user_audio_pcm:   Raw PCM bytes (16kHz, 16-bit, mono) from the user's mic.
        system_prompt:    Short persona + constraints for the session config.
        briefing_context: Full article context injected as fake conversation history.

    Returns:
        (response_audio_pcm, response_transcript)
        response_audio_pcm: Raw PCM 24kHz from Gemini (pass to _pcm_to_mp3).
        response_transcript: Text of Gemini's spoken response (may be empty).
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Session-level config:
    # - response_modalities=["AUDIO"] → Gemini returns audio chunks
    # - system_instruction → persona injected at session start, persists for entire session
    # - speech_config → which preset voice to use for output
    # - output_audio_transcription → also get text alongside audio (for chat history)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            role="user",  # Gemini Live expects system_instruction role="user"
            parts=[types.Part(text=system_prompt)],
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Kore"  # Clear, professional voice
                )
            )
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    audio_chunks: list[bytes] = []
    transcript_parts: list[str] = []

    async with client.aio.live.connect(model=_LIVE_MODEL, config=config) as session:

        # Step 1: Seed briefing context as fake conversation history.
        # This puts the full article context into Gemini's context window
        # without triggering a response — turn_complete=False means
        # "I'm still setting up, don't respond yet."
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
            turn_complete=False,  # don't trigger a response — just prime context
        )

        # Step 2: Send the user's audio question as raw PCM.
        await session.send_realtime_input(
            audio=types.Blob(
                data=user_audio_pcm,
                mime_type="audio/pcm;rate=16000",
            )
        )

        # Step 3: Signal end-of-turn so Gemini knows the user finished speaking.
        await session.send_realtime_input(end_of_turn=True)

        # Step 4: Collect audio response chunks until turn_complete.
        async for response in session.receive():
            # Raw audio data (streamed in chunks)
            if response.data:
                audio_chunks.append(response.data)

            # Structured server content (audio parts + transcription)
            if response.server_content:
                if response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_chunks.append(part.inline_data.data)

                # Text transcript of what Gemini is saying (for chat history display)
                if response.server_content.output_transcription:
                    text = response.server_content.output_transcription.text
                    if text:
                        transcript_parts.append(text)

                # turn_complete = Gemini has finished its response
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

    Takes browser WebM audio, returns (mp3_bytes, transcript_text).
    Runs the entire async session in an isolated thread so it doesn't
    conflict with Streamlit's synchronous execution model.

    Args:
        user_audio_webm: Raw WebM bytes from audio_recorder_streamlit.
        briefing:        The Briefing object produced by the pipeline.
        profile:         The UserProfile for this session.
        chat_history:    Prior Q&A turns (list of {'role': str, 'content': str}).

    Returns:
        (mp3_bytes, transcript): mp3_bytes → st.audio(..., format='audio/mp3')
                                 transcript → display in chat history

    Raises:
        RuntimeError: if GEMINI_API_KEY is missing, ffmpeg not installed,
                      session times out, or Gemini returns empty audio.
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

    # system_instruction: short persona + guardrails (injected at session level)
    system_prompt = (
        f"You are MyET AI, a personal news companion for {profile.name} "
        f"({profile.role}). Answer questions about their news briefing. "
        f"Be conversational and concise (2-4 sentences). "
        f"No markdown, no bullet points — your response will be spoken aloud. "
        f"If a question is outside the briefing scope, say so briefly."
    )

    # briefing_context: full article context (seeded as fake conversation history)
    # Reuse build_context() from conversation.py — same formatting, no duplication
    briefing_context = build_context(briefing, profile)

    # Append recent chat history so Gemini knows what was already discussed
    if chat_history:
        history_lines = []
        for msg in chat_history[-6:]:  # last 6 turns for context window efficiency
            role = "User" if msg["role"] == "user" else "MyET AI"
            history_lines.append(f"{role}: {msg['content']}")
        if history_lines:
            briefing_context += "\n\nPrevious conversation:\n" + "\n".join(history_lines)

    # Run the async Gemini Live session in a new thread.
    # threading.Thread + asyncio.run() = isolated event loop, no Streamlit conflict.
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
```

- [ ] **Step 2: Verify file was created**

```bash
python -c "import ast; ast.parse(open('agents/gemini_live.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add agents/gemini_live.py
git commit -m "feat: add Gemini Live voice Q&A agent with async thread bridge and PCM/MP3 conversion"
```

---

### Task 8: Wire Gemini Live into `app.py` Q&A flow

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace `process_user_question` with Gemini Live primary path**

Replace the existing `process_user_question` function with this version that tries Gemini Live first (audio path) and falls back to text:

```python
def process_user_question(question: str, audio_bytes: bytes = None):
    """
    Process a user question — Gemini Live path (audio) with text fallback.

    audio_bytes: raw WebM from audio_recorder_streamlit (optional).
                 If provided, uses Gemini Live for voice-in/voice-out.
    question:    transcribed text or direct text input (always required for
                 chat history display and text fallback).
    """
    briefing = st.session_state.briefing
    profile = st.session_state.profile

    # Snapshot chat history BEFORE appending current question
    # (passing the snapshot to LLM avoids the question appearing twice in the prompt)
    history_snapshot = list(st.session_state.chat_history)
    st.session_state.chat_history.append({"role": "user", "content": question})

    # ── Path A: Gemini Live (audio in → audio out) ─────────────────────────
    # Only available when: audio bytes present + ffmpeg installed + API key set
    if audio_bytes:
        try:
            from agents.gemini_live import gemini_live_answer
            with st.spinner("MyET AI is responding..."):
                mp3_bytes, response_text = gemini_live_answer(
                    user_audio_webm=audio_bytes,
                    briefing=briefing,
                    profile=profile,
                    chat_history=history_snapshot,
                )

            # Use transcript if available; otherwise show placeholder
            display_text = response_text if response_text else "[Voice response — press play above]"
            st.session_state.chat_history.append({"role": "assistant", "content": display_text})
            st.session_state.last_response_audio = mp3_bytes
            st.rerun()
            return

        except RuntimeError as e:
            # Known failure modes (no ffmpeg, no API key, timeout)
            # — fall through to text path with a visible warning
            st.warning(f"Voice Q&A unavailable ({e}). Using text mode.")
        except Exception as e:
            print(f"[GeminiLive] Unexpected error: {e}")
            st.warning("Voice Q&A error. Using text mode.")

    # ── Path B: Text fallback (original answer_question + TTS chain) ───────
    try:
        from agents.conversation import answer_question
        response = answer_question(
            question=question,
            briefing=briefing,
            profile=profile,
            chat_history=history_snapshot,  # snapshot without current question
        )
    except Exception as e:
        response = f"Sorry, I couldn't process that right now. ({e})"
        print(f"[Q&A] Error: {e}")

    st.session_state.chat_history.append({"role": "assistant", "content": response})

    try:
        from agents.voice import text_to_speech
        audio = text_to_speech(response)
        st.session_state.last_response_audio = audio
    except Exception as e:
        print(f"[Voice] TTS error for Q&A response: {e}")
        st.session_state.last_response_audio = None

    st.rerun()
```

- [ ] **Step 2: Update the voice input section to pass `audio_bytes` to `process_user_question`**

In `render_briefing_page()`, update the `if user_text:` block inside the voice recorder section:

```python
                    if user_text:
                        st.success(f"Heard: {user_text}")
                        # Pass both text AND raw audio — Gemini Live uses audio directly
                        # (bypasses Google Free STT quality issues)
                        process_user_question(user_text, audio_bytes=audio_bytes)
                    else:
                        st.warning("⚠️ Couldn't transcribe audio. Type your question below instead.")
```

- [ ] **Step 3: Update text input path to call without audio_bytes**

In `render_briefing_page()`, in the `col_text` section, the `Send` button handler stays the same (no `audio_bytes` → text fallback path is used automatically):

```python
        if st.button("Send", key="send_btn"):
            question = st.session_state.get("chat_input", "").strip()
            if question:
                process_user_question(question)  # no audio_bytes → text path
```

- [ ] **Step 4: Verify syntax**

```bash
python -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: wire Gemini Live into Q&A flow with text fallback"
```

---

### Task 9: Update `requirements.txt` with new dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Read current requirements.txt**

```bash
cat requirements.txt
```

- [ ] **Step 2: Add new dependencies**

Add these lines to `requirements.txt`:

```
google-genai>=0.7.0
pydub>=0.25.1
```

Note in a comment above them:
```
# Gemini Live voice Q&A (agents/gemini_live.py)
# Also requires ffmpeg at OS level: brew install ffmpeg (macOS) / apt install ffmpeg (Linux)
google-genai>=0.7.0
pydub>=0.25.1
```

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add google-genai and pydub deps for Gemini Live integration"
```

---

## Chunk 4: Minor Bug Fixes

### Task 10: Fix RSS article count + NewsAPI key guard

**Files:**
- Modify: `agents/ingestion.py`

- [ ] **Step 1: Fix integer division in RSS fetcher**

In `fetch_from_rss()`, replace:
```python
for entry in feed.entries[:MAX_ARTICLES // len(feeds)]:
```
with:
```python
import math
per_feed = math.ceil(MAX_ARTICLES / len(feeds))  # ceiling so we don't lose articles
for entry in feed.entries[:per_feed]:
```

Add `import math` at the top of the file.

- [ ] **Step 2: Fix empty API key guard**

In `fetch_from_newsapi()`, replace:
```python
if NEWS_API_KEY == "YOUR_NEWSAPI_KEY_HERE":
    return []
```
with:
```python
if not NEWS_API_KEY or NEWS_API_KEY == "YOUR_NEWSAPI_KEY_HERE":
    return []
```

- [ ] **Step 3: Commit**

```bash
git add agents/ingestion.py
git commit -m "fix: use ceiling division for RSS per-feed limit, guard empty NewsAPI key"
```

---

### Task 11: Smoke test the full pipeline locally

- [ ] **Step 1: Verify imports work**

```bash
python -c "
from utils.llm import ask_llm, ask_llm_json
from agents.ingestion import ingest
from agents.voice import text_to_speech, speech_to_text
from agents.gemini_live import gemini_live_answer
print('All imports OK')
"
```

Expected: `All imports OK` (may warn about missing google-genai if not installed yet)

- [ ] **Step 2: Install new dependencies**

```bash
pip install google-genai>=0.7.0 pydub>=0.25.1
```

- [ ] **Step 3: Run the app**

```bash
streamlit run app.py
```

Manually verify:
- Profile page loads
- Briefing generates (no duplicate LLM calls without gaps)
- Article cards render without raw HTML tags visible
- Q&A text input works (fallback path)
- If ffmpeg + GEMINI_API_KEY set: voice Q&A uses Gemini Live path

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: verify smoke test passes after all bug fixes and Gemini Live integration"
```
