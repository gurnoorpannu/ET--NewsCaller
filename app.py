"""MyET AI + Voice Companion — Streamlit App."""
import streamlit as st
from models.schemas import UserProfile
from pipeline import run_pipeline
from agents.voice import text_to_speech, speech_to_text
from agents.conversation import answer_question

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
        "step": "profile",  # profile -> loading -> briefing -> chat
        "profile": None,
        "briefing": None,
        "chat_history": [],
        "briefing_audio": None,
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
    st.info(f"Preparing your personalized briefing, {profile.name}...")

    progress = st.progress(0, text="Starting pipeline...")

    try:
        # Run the full pipeline
        progress.progress(10, text="📡 Fetching news articles...")
        from agents.ingestion import ingest
        articles = ingest(interests=profile.interests)

        if not articles:
            st.error("Could not fetch any articles. Check your API keys or internet connection.")
            if st.button("← Go Back"):
                st.session_state.step = "profile"
                st.rerun()
            return

        progress.progress(30, text=f"🔍 Analyzing {len(articles)} articles...")
        from agents.understanding import understand
        analyzed = understand(articles)

        progress.progress(50, text="🧠 Understanding your profile...")
        from agents.profiling import interpret_profile
        profile_data = interpret_profile(profile)

        progress.progress(70, text="🎯 Personalizing for you...")
        from agents.personalization import personalize
        ranked = personalize(analyzed, profile, profile_data)

        progress.progress(85, text="📝 Generating your briefing...")
        from agents.briefing import generate_briefing
        briefing = generate_briefing(ranked, profile, profile_data)

        progress.progress(95, text="🎙️ Preparing voice...")
        audio_bytes = text_to_speech(briefing.summary_text)

        st.session_state.briefing = briefing
        st.session_state.briefing_audio = audio_bytes
        progress.progress(100, text="✅ Done!")

        st.session_state.step = "briefing"
        st.rerun()

    except Exception as e:
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

        st.markdown(f"""
        <div class='article-card'>
            <h4>{i}. {article.title}</h4>
            <span class='relevance-badge {badge_class}'>{badge_text}</span>
            &nbsp;&nbsp;<span style='color:#b2bec3;'>{article.source}</span>
            <p style='margin-top:0.5rem;'>{article.description[:200]}</p>
            <p style='color:#6c5ce7; font-style:italic;'>💡 {article.why_it_matters}</p>
            <small>Topics: {', '.join(article.topics)} | Sentiment: {article.sentiment}</small>
        </div>
        """, unsafe_allow_html=True)

    # Interactive Q&A Section
    st.markdown("---")
    st.subheader("💬 Ask Me Anything")
    st.caption("Ask follow-up questions about any article, or request a deeper explanation.")

    # Chat history display
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"<div class='chat-msg user-msg'>🗣️ <b>You:</b> {msg['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='chat-msg ai-msg'>🤖 <b>MyET AI:</b> {msg['content']}</div>", unsafe_allow_html=True)

    # Voice input section
    col_voice, col_text = st.columns([1, 2])

    with col_voice:
        try:
            from audio_recorder_streamlit import audio_recorder
            audio_bytes = audio_recorder(
                text="🎤 Tap to speak",
                recording_color="#6c5ce7",
                neutral_color="#b2bec3",
                pause_threshold=2.0,
            )
            if audio_bytes:
                user_text = speech_to_text(audio_bytes)
                if user_text:
                    st.success(f"Heard: {user_text}")
                    process_user_question(user_text)
                else:
                    st.warning("Couldn't understand. Try again or type below.")
        except ImportError:
            st.info("Voice input requires audio-recorder-streamlit package.")

    with col_text:
        user_input = st.text_input("Or type your question:", key="chat_input", placeholder="e.g., Tell me more about article 1")
        if st.button("Send", key="send_btn"):
            if user_input:
                process_user_question(user_input)

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


def process_user_question(question: str):
    """Process a user question and generate response."""
    briefing = st.session_state.briefing
    profile = st.session_state.profile

    # Add user message
    st.session_state.chat_history.append({"role": "user", "content": question})

    # Get AI response
    response = answer_question(
        question=question,
        briefing=briefing,
        profile=profile,
        chat_history=st.session_state.chat_history,
    )

    # Add AI response
    st.session_state.chat_history.append({"role": "assistant", "content": response})

    # Generate voice response
    try:
        audio = text_to_speech(response)
        st.session_state["last_response_audio"] = audio
    except Exception:
        pass

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
