"""MyET AI + Voice Companion — Streamlit App."""
import hashlib
import html as html_lib  # for escaping RSS/LLM content in unsafe_allow_html blocks
import streamlit as st
from models.schemas import UserProfile

# --- Page Config ---
st.set_page_config(
    page_title="MyET AI — Voice News Companion",
    page_icon="🎙️",
    layout="wide",
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
    }
    .article-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 1.2rem;
        margin: 0.8rem 0;
        border-left: 4px solid #6c5ce7;
    }
    .article-card h4 { margin: 0 0 0.5rem 0; }
    .relevance-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .high-relevance { background: #00b894; color: white; }
    .med-relevance { background: #fdcb6e; color: black; }
    .low-relevance { background: #e17055; color: white; }
    .chat-msg {
        padding: 0.8rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .user-msg { background: #2d3436; }
    .ai-msg { background: #1e1e2e; border-left: 3px solid #6c5ce7; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    defaults = {
        "step": "profile",         # profile -> loading -> briefing
        "profile": None,
        "briefing": None,
        "chat_history": [],
        "briefing_audio": None,
        "last_response_audio": None,
        "pipeline_running": False, # guard against double pipeline execution on rerun
        "last_audio_hash": None,   # dedup: skip reprocessing same audio bytes on rerun
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_profile_page():
    """Step 1: Collect user profile."""
    st.markdown("<h1 class='main-header'>🎙️ MyET AI — Voice News Companion</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color: #b2bec3;'>News that adapts to you. Delivered by voice.</p>", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Tell us about yourself")
    st.caption("This helps us personalize your news experience.")

    col1, col2 = st.columns(2)

    with col1:
        name = st.text_input("Your name", placeholder="e.g., Gurnoor")
        role = st.selectbox("What best describes you?", [
            "Investor / Trader",
            "Tech Professional",
            "Startup Founder / Entrepreneur",
            "Student",
            "Business Executive",
            "Policy / Government",
            "Journalist / Media",
            "General Reader",
        ])

    with col2:
        interests = st.multiselect("Topics you care about", [
            "Technology",
            "Stock Markets",
            "Startups",
            "AI / Machine Learning",
            "Economy / Finance",
            "Crypto / Blockchain",
            "Geopolitics",
            "Healthcare",
            "Climate / Energy",
            "Sports",
            "Entertainment",
            "Science",
            "Real Estate",
            "Education",
        ], default=["Technology", "AI / Machine Learning"])

        depth = st.select_slider(
            "How detailed should your briefing be?",
            options=["brief", "medium", "detailed"],
            value="medium",
        )

    st.markdown("---")

    if st.button("🚀 Generate My Briefing", type="primary", use_container_width=True):
        if not name:
            st.warning("Please enter your name!")
            return

        profile = UserProfile(
            name=name,
            role=role,
            interests=[i.lower() for i in interests],
            preferred_depth=depth,
        )
        st.session_state.profile = profile
        st.session_state.step = "loading"
        st.rerun()


def render_loading_page():
    """Step 2: Run pipeline with progress."""
    st.markdown("<h1 class='main-header'>🎙️ MyET AI</h1>", unsafe_allow_html=True)

    profile = st.session_state.profile

    # Guard: if a rerun fires while the pipeline is already running
    # (e.g. browser heartbeat), don't start a second execution
    if st.session_state.get("pipeline_running"):
        st.info(f"Preparing your personalized briefing, {profile.name}...")
        st.spinner("Pipeline is running...")
        return

    st.session_state.pipeline_running = True
    st.info(f"Preparing your personalized briefing, {profile.name}...")
    progress = st.progress(0, text="Starting pipeline...")

    try:
        # run_pipeline() handles agents 1-5 in sequence with rate-limit gaps
        # (pipeline.py enforces _CALL_GAP = 6s between LLM calls)
        progress.progress(10, text="📡 Fetching + analyzing + personalizing...")
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


def render_briefing_page():
    """Step 3: Show briefing + voice player + Q&A."""
    briefing = st.session_state.briefing
    profile = st.session_state.profile

    # Header
    st.markdown("<h1 class='main-header'>🎙️ Your Personalized Briefing</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:#b2bec3;'>Tailored for {profile.name} — {profile.role}</p>", unsafe_allow_html=True)

    # Voice Player
    st.markdown("---")
    st.subheader("🔊 Listen to Your Briefing")

    if st.session_state.briefing_audio:
        st.audio(st.session_state.briefing_audio, format="audio/mp3")

    with st.expander("📄 Read the briefing text", expanded=False):
        st.write(briefing.summary_text)

    # Article Cards
    st.markdown("---")
    st.subheader("📰 Top Stories For You")

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

        # Escape all dynamic values before injecting into HTML —
        # RSS titles/descriptions can contain <script> tags or HTML entities
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

    # Interactive Q&A Section
    st.markdown("---")
    st.subheader("💬 Ask Me Anything")
    st.caption("Ask follow-up questions about any article, or request a deeper explanation.")

    # Chat history display — escape content to prevent XSS
    for msg in st.session_state.chat_history:
        content_safe = html_lib.escape(msg["content"])
        if msg["role"] == "user":
            st.markdown(f"<div class='chat-msg user-msg'>🗣️ <b>You:</b> {content_safe}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-msg ai-msg'>🤖 <b>MyET AI:</b> {content_safe}</div>", unsafe_allow_html=True)

    # Voice input section
    col_voice, col_text = st.columns([1, 2])

    with col_voice:
        try:
            from audio_recorder_streamlit import audio_recorder
            from agents.voice import speech_to_text
            recorded = audio_recorder(
                text="🎤 Tap to speak",
                recording_color="#6c5ce7",
                neutral_color="#b2bec3",
                pause_threshold=2.0,
            )
            if recorded:
                # Dedup: audio_recorder returns the same bytes on every Streamlit
                # rerun until new audio is recorded — skip if we already processed this
                audio_hash = hashlib.md5(recorded).hexdigest()
                if audio_hash != st.session_state.get("last_audio_hash"):
                    st.session_state.last_audio_hash = audio_hash
                    with st.spinner("Transcribing..."):
                        user_text = speech_to_text(recorded)
                    if user_text:
                        st.success(f"Heard: {user_text}")
                        # Pass raw audio too — Gemini Live uses it directly,
                        # bypassing Google Free STT quality issues
                        process_user_question(user_text, audio_bytes=recorded)
                    else:
                        st.warning("⚠️ Couldn't transcribe audio. Type your question below instead.")
        except ImportError:
            st.info("Voice input requires audio-recorder-streamlit package.")

    with col_text:
        st.text_input("Or type your question:", key="chat_input", placeholder="e.g., Tell me more about article 1")
        if st.button("Send", key="send_btn"):
            # Read directly from session_state — reliable after button click rerun
            question = st.session_state.get("chat_input", "").strip()
            if question:
                process_user_question(question)

    # Sidebar controls
    with st.sidebar:
        st.markdown("### Controls")
        if st.button("🔄 New Briefing", use_container_width=True):
            st.session_state.step = "profile"
            st.session_state.briefing = None
            st.session_state.chat_history = []
            st.session_state.briefing_audio = None
            st.rerun()

        st.markdown("---")
        st.markdown("### About")
        st.markdown("""
        **MyET AI + Voice Companion**

        A multi-agent AI system that:
        - Ingests real-time news
        - Understands content deeply
        - Personalizes for YOU
        - Delivers via voice

        *Built for ET AI Hackathon — Track 8*
        """)


def process_user_question(question: str, audio_bytes: bytes = None):
    """
    Process a user question — Gemini Live path (audio) with text fallback.

    audio_bytes: raw WebM from audio_recorder_streamlit (optional).
                 If provided, tries Gemini Live for voice-in/voice-out.
    question:    text of the question (always required for chat history display).
    """
    briefing = st.session_state.briefing
    profile = st.session_state.profile

    # Snapshot history BEFORE appending current question.
    # answer_question() adds "User's question: {question}" separately,
    # so passing the post-append history would make the question appear twice.
    history_snapshot = list(st.session_state.chat_history)
    st.session_state.chat_history.append({"role": "user", "content": question})

    # ── Path A: Gemini Live (audio in → audio out) ─────────────────────────
    # Only attempted when audio bytes are present (voice input was used).
    # Eliminates the 3-step STT→LLM→TTS chain with a single WebSocket session.
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
            display_text = response_text if response_text else "[Voice response — press play above]"
            st.session_state.chat_history.append({"role": "assistant", "content": display_text})
            st.session_state.last_response_audio = mp3_bytes
            st.rerun()
            return
        except RuntimeError as e:
            # Known failure modes: no ffmpeg, no API key, timeout
            st.warning(f"Voice Q&A unavailable ({e}). Using text mode.")
        except Exception as e:
            print(f"[GeminiLive] Unexpected error: {e}")
            st.warning("Voice Q&A error. Using text mode.")

    # ── Path B: Text fallback (original answer_question + TTS chain) ───────
    from agents.conversation import answer_question
    from agents.voice import text_to_speech
    try:
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
        audio = text_to_speech(response)
        st.session_state.last_response_audio = audio
    except Exception as e:
        print(f"[Voice] TTS error for Q&A response: {e}")
        st.session_state.last_response_audio = None

    st.rerun()


# --- Main ---
def main():
    init_session_state()

    if st.session_state.step == "profile":
        render_profile_page()
    elif st.session_state.step == "loading":
        render_loading_page()
    elif st.session_state.step == "briefing":
        render_briefing_page()

        # Auto-play last response audio
        if "last_response_audio" in st.session_state and st.session_state.last_response_audio:
            st.audio(st.session_state.last_response_audio, format="audio/mp3")
            st.session_state.last_response_audio = None


if __name__ == "__main__":
    main()
