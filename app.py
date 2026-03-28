"""MyET AI + Voice Companion — Streamlit App."""
import html as html_lib  # for escaping RSS/LLM content in unsafe_allow_html blocks
import streamlit as st
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from models.schemas import UserProfile, ScheduledCall
from shared_state import scheduled_calls, calls_lock

# --- Page Config ---
st.set_page_config(
    page_title="MyET AI — Voice News Companion",
    page_icon="▶",
    layout="wide",
)

# =============================================================================
# GLOBAL CSS
# Design system:
#   Base:    #0f0f0f (near-black canvas)
#   Surface: #181818 (card/input surfaces)
#   Border:  #2a2a2a (subtle dividers)
#   Text:    #e8e0d0 (warm off-white — WCAG AA on #0f0f0f: 13.2:1)
#   Muted:   #8a8278 (secondary text — 4.7:1 on #0f0f0f ✓ AA)
#   Accent:  #c8a96e (amber — 5.9:1 on #0f0f0f ✓ AA)
#   Radius:  6px (one value everywhere)
#   Fonts:   'IBM Plex Mono' for headings/labels, 'Source Serif 4' for body
#
# Sentiment border palette:
#   Positive: #4caf50  (green)
#   Neutral:  #9e9e9e  (mid-grey)
#   Negative: #ef5350  (red)
# =============================================================================

GLOBAL_CSS = """
<style>
/* ── Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;1,8..60,300&display=swap');

/* ── Reset & Base ── */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #0f0f0f !important;
    color: #e8e0d0 !important;
    font-family: 'Source Serif 4', Georgia, serif !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* ── Typography scale ── */
h1, h2, h3, h4, h5, h6 {
    font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
    color: #e8e0d0 !important;
    letter-spacing: -0.02em;
}

/* ── Streamlit widget label overrides ── */
[data-testid="stWidgetLabel"] label,
[data-testid="stWidgetLabel"] p,
label, .stSelectbox label,
[data-baseweb="form-control-label"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.72rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
    color: #8a8278 !important;
}

/* ── Inputs / Textareas ── */
input[type="text"], textarea,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background: #181818 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 6px !important;
    color: #e8e0d0 !important;
    font-family: 'Source Serif 4', serif !important;
    font-size: 0.95rem !important;
    transition: border-color 0.15s ease;
}
input[type="text"]:focus, textarea:focus,
[data-baseweb="input"] input:focus {
    border-color: #c8a96e !important;
    box-shadow: 0 0 0 2px rgba(200,169,110,0.12) !important;
    outline: none !important;
}
input::placeholder { color: #4a4440 !important; }

/* ── Selectbox ── */
[data-baseweb="select"] > div {
    background: #181818 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 6px !important;
    color: #e8e0d0 !important;
}
[data-baseweb="select"] > div:hover {
    border-color: #c8a96e !important;
}

/* ── Multiselect ── */
[data-baseweb="tag"] {
    background: #2a2a2a !important;
    border-radius: 6px !important;
}
[data-testid="stMultiSelect"] [data-baseweb="input"] {
    background: #181818 !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
    background-color: #c8a96e !important;
    border-color: #c8a96e !important;
}
[data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stThumbValue"] {
    color: #c8a96e !important;
}

/* ── Primary Button ── */
[data-testid="stButton"] > button[kind="primary"],
button[kind="primary"] {
    background: #c8a96e !important;
    color: #0f0f0f !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    padding: 0.6rem 1.6rem !important;
    transition: background 0.15s, box-shadow 0.15s;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #dbbf82 !important;
    box-shadow: 0 2px 12px rgba(200,169,110,0.3) !important;
}

/* ── Secondary Button ── */
[data-testid="stButton"] > button:not([kind="primary"]) {
    background: transparent !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 6px !important;
    color: #8a8278 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.75rem !important;
    transition: border-color 0.15s, color 0.15s;
}
[data-testid="stButton"] > button:not([kind="primary"]):hover {
    border-color: #c8a96e !important;
    color: #c8a96e !important;
}

/* ── st.info / st.warning / st.error / st.success ── */
[data-testid="stAlert"] {
    border-radius: 6px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
}

/* ── Expander ── */
[data-testid="stExpander"] details {
    background: #181818 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 6px !important;
}
[data-testid="stExpander"] summary {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 0.8rem !important;
    color: #8a8278 !important;
}
[data-testid="stExpander"] summary:hover {
    color: #e8e0d0 !important;
}

/* ── Audio player ── */
audio {
    width: 100% !important;
    border-radius: 6px !important;
    filter: invert(1) hue-rotate(180deg) brightness(0.85);
}

/* ── Divider ── */
hr {
    border: none !important;
    border-top: 1px solid #2a2a2a !important;
    margin: 1.5rem 0 !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #111111 !important;
    border-right: 1px solid #1e1e1e !important;
}
[data-testid="stSidebar"] * {
    font-family: 'IBM Plex Mono', monospace !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #0f0f0f; }
::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: #3a3a3a; }

/* =========================================================
   PROFILE PAGE — Role Selector Cards
   Hidden radio input, styled label acts as the card.
   JS toggles the .selected class on click.
   ========================================================= */
.role-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin: 8px 0 16px 0;
}
.role-card {
    background: #181818;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 10px 14px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
    user-select: none;
}
.role-card:hover {
    border-color: #c8a96e;
    background: #1e1c18;
    box-shadow: 0 0 0 1px rgba(200,169,110,0.15);
}
.role-card.selected {
    border-color: #c8a96e;
    background: #1e1c18;
    box-shadow: 0 0 0 2px rgba(200,169,110,0.2);
}
.role-card .role-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.78rem;
    font-weight: 600;
    color: #e8e0d0;
    letter-spacing: 0.02em;
    display: block;
    margin-bottom: 2px;
}
.role-card.selected .role-title { color: #c8a96e; }
.role-card .role-desc {
    font-family: 'Source Serif 4', serif;
    font-size: 0.72rem;
    color: #8a8278;
    font-style: italic;
}

/* PROFILE PAGE — Interest suggestion pills */
.pill-section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #8a8278;
    margin: 6px 0 6px 0;
    display: block;
}

/* Pill buttons rendered via st.button — override to look like pills */
.pill-row [data-testid="stButton"] > button {
    background: #181818 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 20px !important;
    padding: 2px 12px !important;
    font-size: 0.72rem !important;
    font-family: 'IBM Plex Mono', monospace !important;
    color: #8a8278 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
    height: auto !important;
    line-height: 1.6 !important;
    min-height: unset !important;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.pill-row [data-testid="stButton"] > button:hover {
    border-color: #c8a96e !important;
    color: #c8a96e !important;
    background: #1e1c18 !important;
}
.pill-row-active [data-testid="stButton"] > button {
    background: #1e1c18 !important;
    border-color: #c8a96e !important;
    color: #c8a96e !important;
}

/* =========================================================
   LOADING PAGE — Pipeline stage log
   ========================================================= */
.pipeline-log {
    background: #111;
    border: 1px solid #1e1e1e;
    border-radius: 6px;
    padding: 20px 24px;
    font-family: 'IBM Plex Mono', monospace;
    max-width: 640px;
    margin: 24px auto;
}
.pipeline-log-header {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #4a4440;
    border-bottom: 1px solid #1e1e1e;
    padding-bottom: 10px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
}
.stage-row {
    display: flex;
    align-items: baseline;
    gap: 12px;
    padding: 6px 0;
    border-bottom: 1px solid #181818;
    font-size: 0.82rem;
}
.stage-row:last-child { border-bottom: none; }
.stage-status {
    width: 12px;
    flex-shrink: 0;
    text-align: center;
    color: #4a4440;
}
.stage-status.pending  { color: #4a4440; }
.stage-status.running  { color: #c8a96e; }
.stage-status.done     { color: #4caf50; }
.stage-status.error    { color: #ef5350; }
.stage-name {
    flex: 1;
    color: #8a8278;
}
.stage-name.running { color: #e8e0d0; font-weight: 500; }
.stage-name.done    { color: #8a8278; }
.stage-detail {
    font-size: 0.72rem;
    color: #4a4440;
    text-align: right;
    min-width: 120px;
}
.stage-detail.running { color: #c8a96e; }
.stage-detail.done    { color: #4a4440; }

/* =========================================================
   BRIEFING PAGE — Article Cards
   ========================================================= */
.article-card {
    background: #141414;
    border-radius: 6px;
    border: 1px solid #2a2a2a;
    border-left: 3px solid #2a2a2a;   /* overridden per-sentiment below */
    padding: 18px 20px;
    margin: 12px 0;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.article-card:hover {
    box-shadow: 0 2px 16px rgba(0,0,0,0.4);
    border-color: #3a3a3a;
}
/* Sentiment left-border — the ONLY sentiment indicator (no emoji) */
.article-card.sentiment-positive { border-left-color: #4caf50; }
.article-card.sentiment-neutral  { border-left-color: #9e9e9e; }
.article-card.sentiment-negative { border-left-color: #ef5350; }

.article-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1rem;
    font-weight: 600;
    color: #e8e0d0;
    margin: 0 0 8px 0;
    line-height: 1.4;
}
.article-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    margin-bottom: 10px;
}
.article-source {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #c8a96e;
}
.article-date {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #4a4440;
}
.article-topics {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    color: #4a4440;
}
.article-body {
    font-family: 'Source Serif 4', serif;
    font-size: 0.9rem;
    color: #b0a898;
    line-height: 1.6;
    margin: 0 0 10px 0;
}
.article-insight {
    font-family: 'Source Serif 4', serif;
    font-style: italic;
    font-size: 0.85rem;
    color: #8a8278;
    border-top: 1px solid #1e1e1e;
    padding-top: 10px;
    margin-top: 6px;
    line-height: 1.5;
}
.relevance-badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 6px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.badge-high { background: rgba(76,175,80,0.15);  color: #4caf50; border: 1px solid rgba(76,175,80,0.3); }
.badge-med  { background: rgba(200,169,110,0.15); color: #c8a96e; border: 1px solid rgba(200,169,110,0.3); }
.badge-low  { background: rgba(239,83,80,0.1);   color: #ef5350; border: 1px solid rgba(239,83,80,0.2); }

/* =========================================================
   BRIEFING PAGE — Audio Player Section
   ========================================================= */
.audio-section {
    background: #141414;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 24px 28px;
    margin: 16px 0 24px 0;
}
.audio-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #8a8278;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.audio-label::before {
    content: '';
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #c8a96e;
}

/* =========================================================
   BRIEFING PAGE — Chat Thread
   ========================================================= */
.chat-thread {
    background: #111;
    border: 1px solid #1e1e1e;
    border-radius: 6px;
    padding: 16px;
    max-height: 480px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 14px;
}
.chat-bubble {
    max-width: 80%;
    padding: 10px 14px;
    border-radius: 6px;
    font-family: 'Source Serif 4', serif;
    font-size: 0.88rem;
    line-height: 1.55;
}
/* User bubbles — right-aligned */
.chat-bubble-user {
    align-self: flex-end;
    background: #1e1c18;
    border: 1px solid #c8a96e;
    color: #e8e0d0;
    border-bottom-right-radius: 2px;
}
.chat-bubble-user .bubble-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #c8a96e;
    margin-bottom: 4px;
}
/* AI bubbles — left-aligned */
.chat-bubble-ai {
    align-self: flex-start;
    background: #181818;
    border: 1px solid #2a2a2a;
    color: #b0a898;
    border-bottom-left-radius: 2px;
}
.chat-bubble-ai .bubble-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #8a8278;
    margin-bottom: 4px;
}
.chat-empty {
    text-align: center;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: #2a2a2a;
    padding: 32px 0;
    letter-spacing: 0.06em;
}

/* =========================================================
   UTILITY
   ========================================================= */
.section-label {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #4a4440;
    margin: 24px 0 12px 0;
    display: flex;
    align-items: center;
    gap: 10px;
}
.section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #1e1e1e;
}

.page-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.6rem;
    font-weight: 600;
    color: #e8e0d0;
    letter-spacing: -0.03em;
    margin: 0;
    line-height: 1.2;
}
.page-subtitle {
    font-family: 'Source Serif 4', serif;
    font-style: italic;
    font-size: 0.95rem;
    color: #8a8278;
    margin: 6px 0 0 0;
}

/* Column gap tightening */
[data-testid="stHorizontalBlock"] { gap: 24px !important; }
</style>
"""

# --- Role definitions (title + one-line description) ---
# Each entry becomes a selector card on the profile screen.
ROLES = [
    ("Investor / Trader",           "Markets, earnings, macro signals"),
    ("Tech Professional",           "Products, engineering, industry moves"),
    ("Startup Founder",             "Funding, competitors, market shifts"),
    ("Student",                     "Learning-oriented, broad context"),
    ("Business Executive",          "Strategy, M&A, sector trends"),
    ("Policy / Government",         "Regulation, economy, geopolitics"),
    ("Journalist / Media",          "Story angles, sources, breaking news"),
    ("General Reader",              "Curious, no specific vertical"),
]

# --- Suggested interest pills (shown beneath the multiselect) ---
# Clicking a pill adds it to the multiselect selection.
ALL_INTERESTS = [
    "Technology", "Stock Markets", "Startups", "AI / Machine Learning",
    "Economy / Finance", "Crypto / Blockchain", "Geopolitics", "Healthcare",
    "Climate / Energy", "Sports", "Entertainment", "Science",
    "Real Estate", "Education",
]
SUGGESTED_PILLS = ["Technology", "AI / Machine Learning", "Stock Markets",
                   "Startups", "Economy / Finance", "Geopolitics"]


def init_session_state():
    """Initialize all session state variables with defaults."""
    defaults = {
        "step": "profile",         # profile -> loading -> briefing
        "profile": None,
        "briefing": None,
        "chat_history": [],
        "briefing_audio": None,
        "last_response_audio": None,
        # Role/interest selectors (profile page state)
        "selected_role": ROLES[0][0],
        "selected_interests": {"Technology", "AI / Machine Learning"},
        # Pipeline guard: prevents double execution on Streamlit reruns
        "pipeline_running": False,
        # Phone number persisted across reruns so user doesn't re-type after scheduling
        "call_phone_number": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# =============================================================================
# PROFILE PAGE
# =============================================================================

def render_role_selector():
    """
    Render 8 role cards in a 2-column CSS grid.

    Streamlit limitation: there is no native radio-card widget.
    Workaround: inject the card HTML and capture selection via
    st.session_state + st.button (one hidden button per card).
    Since clicking inside an HTML block can't trigger Python,
    we render each card as a full st.button call wrapped in a
    CSS class that styles it like a card.
    """
    # Build the role grid using columns of buttons.
    # Two buttons per row to mimic a 2-col card grid.
    st.markdown('<span class="pill-section-label">Your role</span>', unsafe_allow_html=True)
    rows = [ROLES[i:i+2] for i in range(0, len(ROLES), 2)]
    for row in rows:
        cols = st.columns(len(row))
        for col, (role_title, role_desc) in zip(cols, row):
            is_selected = st.session_state.selected_role == role_title
            # CSS class applied via a container div injected before the button
            selected_class = "role-card selected" if is_selected else "role-card"
            # Render the card as styled HTML + a transparent button overlay.
            # The button click updates session state; the HTML provides visual style.
            col.markdown(f"""
            <div class="{selected_class}">
                <span class="role-title">{role_title}</span>
                <span class="role-desc">{role_desc}</span>
            </div>
            """, unsafe_allow_html=True)
            # Invisible select button — width fills the card column
            if col.button("select", key=f"role_{role_title}", use_container_width=True):
                st.session_state.selected_role = role_title
                st.rerun()

    # Streamlit limitation: the HTML card and the button are separate elements,
    # so the button renders below the card. We push the button up using negative
    # margin via injected CSS so it visually overlays the card.
    st.markdown("""
    <style>
    /* Pull each role-select button up to overlap its card above */
    [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button {
        margin-top: -62px !important;
        height: 58px !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        opacity: 0 !important;
        cursor: pointer !important;
    }
    [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button:hover {
        opacity: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)


def render_interest_pills(current_interests: set) -> set:
    """
    Render quick-add suggestion pills beneath the multiselect.
    Returns the (possibly updated) interest set.

    Streamlit limitation: buttons cause a full rerun, so pill
    clicks update session_state.selected_interests then rerun.
    The multiselect is initialized from this same state key so
    they stay in sync.
    """
    st.markdown('<span class="pill-section-label">Quick add</span>', unsafe_allow_html=True)
    st.markdown('<div class="pill-row">', unsafe_allow_html=True)

    # Render pills as a horizontal flow using columns
    cols = st.columns(len(SUGGESTED_PILLS))
    for col, pill in zip(cols, SUGGESTED_PILLS):
        is_active = pill in current_interests
        # Apply active class by wrapping in a div — same overlay trick as role cards
        if is_active:
            col.markdown(f'<div class="pill-row-active">', unsafe_allow_html=True)
        if col.button(("+ " if not is_active else "✓ ") + pill, key=f"pill_{pill}"):
            updated = set(current_interests)
            if pill in updated:
                updated.discard(pill)
            else:
                updated.add(pill)
            st.session_state.selected_interests = updated
            st.rerun()
        if is_active:
            col.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
    return current_interests


def render_profile_page():
    """Step 1: Collect user profile with card-based role selector and interest pills."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    # Page header
    st.markdown("""
    <div style="padding: 32px 0 8px 0;">
        <p class="page-title">MyET AI</p>
        <p class="page-subtitle">Voice-first news intelligence, personalized to you.</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label">Your profile</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])

    with col1:
        # Name field
        st.markdown('<span class="pill-section-label">Name</span>', unsafe_allow_html=True)
        name = st.text_input("Name", placeholder="e.g., Gurnoor", label_visibility="collapsed")

        # Role selector cards
        render_role_selector()

    with col2:
        # Multiselect — initialized from session state so pills stay in sync
        st.markdown('<span class="pill-section-label">Topics you care about</span>', unsafe_allow_html=True)
        interests = st.multiselect(
            "Topics",
            ALL_INTERESTS,
            default=list(st.session_state.selected_interests),
            key="interests_multiselect",
            label_visibility="collapsed",
        )
        # Keep session state in sync with multiselect (user may have deselected via the widget)
        st.session_state.selected_interests = set(interests)

        # Interest suggestion pills
        render_interest_pills(st.session_state.selected_interests)

        # Briefing depth slider
        st.markdown('<span class="pill-section-label" style="margin-top:16px; display:block;">Briefing depth</span>', unsafe_allow_html=True)
        depth = st.select_slider(
            "Depth",
            options=["brief", "medium", "detailed"],
            value="medium",
            label_visibility="collapsed",
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # CTA button
    if st.button("Generate briefing", type="primary", use_container_width=True):
        if not name:
            st.warning("Enter your name to continue.")
            return

        profile = UserProfile(
            name=name,
            role=st.session_state.selected_role,
            interests=[i.lower() for i in interests],
            preferred_depth=depth,
        )
        st.session_state.profile = profile
        st.session_state.step = "loading"
        st.rerun()


# =============================================================================
# LOADING PAGE
# =============================================================================

# Pipeline stage definitions: (label, detail_fn)
# detail_fn receives the previous stage's output count (or None) and returns
# the detail string shown in the "detail" column while the stage is running.
PIPELINE_STAGES = [
    ("Ingestion",        "Fetching articles from NewsAPI + ET RSS"),
    ("Understanding",    "Extracting topics, entities, sentiment"),
    ("Profiling",        "Expanding user preference model"),
    ("Personalization",  "Scoring articles for relevance"),
    ("Briefing",         "Generating conversational summary"),
]
# Status symbols (Unicode, no emoji)
SYM_PENDING = "·"
SYM_RUNNING = "▶"
SYM_DONE    = "✓"
SYM_ERROR   = "✗"


def _stage_html(statuses: list, details: list) -> str:
    """
    Render the pipeline log HTML.
    statuses: list of 'pending'|'running'|'done'|'error' strings
    details:  list of detail strings (shown in right column)

    HTML must not be indented with leading spaces on each line: Streamlit's
    Markdown parser treats 4+ space indents as code blocks, which shows raw
    tags instead of rendering them.
    """
    rows_parts: list[str] = []
    for i, (label, _) in enumerate(PIPELINE_STAGES):
        st_str = statuses[i]
        sym = {"pending": SYM_PENDING, "running": SYM_RUNNING,
               "done": SYM_DONE, "error": SYM_ERROR}.get(st_str, SYM_PENDING)
        detail_safe = html_lib.escape(details[i] or "")
        rows_parts.append(
            f'<div class="stage-row">'
            f'<span class="stage-status {st_str}">{sym}</span>'
            f'<span class="stage-name {st_str}">{i + 1}. {html_lib.escape(label)}</span>'
            f'<span class="stage-detail {st_str}">{detail_safe}</span>'
            f"</div>"
        )
    rows_html = "".join(rows_parts)
    done_n = sum(1 for s in statuses if s == "done")
    total_n = len(PIPELINE_STAGES)
    return (
        f'<div class="pipeline-log">'
        f'<div class="pipeline-log-header">'
        f"<span>Pipeline</span>"
        f"<span>{done_n}/{total_n} complete</span>"
        f"</div>"
        f"{rows_html}"
        f"</div>"
    )


def render_loading_page():
    """
    Step 2: Run each of the 5 pipeline agents with a live log.
    Each stage transitions: pending -> running -> done (or error).
    The log is a single st.empty() block updated in-place.
    """
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div style="padding: 24px 0 4px 0;">
        <p class="page-title">MyET AI</p>
    </div>
    """, unsafe_allow_html=True)

    profile = st.session_state.profile

    # Guard: if a rerun fires while the pipeline is already running
    # (e.g. browser heartbeat), don't start a second execution
    if st.session_state.get("pipeline_running"):
        st.spinner("Pipeline is running...")
        return

    st.session_state.pipeline_running = True

    st.markdown(
        f'<p style="font-family:\'IBM Plex Mono\',monospace;font-size:0.8rem;color:#8a8278;">'
        f'Building briefing for {profile.name} &mdash; {profile.role}</p>',
        unsafe_allow_html=True,
    )

    # Initialize stage tracking
    statuses = ["pending"] * len(PIPELINE_STAGES)
    details  = [""] * len(PIPELINE_STAGES)

    log_placeholder = st.empty()

    def update_log():
        log_placeholder.markdown(_stage_html(statuses, details), unsafe_allow_html=True)

    update_log()

    try:
        # ── Stage 0: Ingestion ──────────────────────────────────────────────
        statuses[0] = "running"
        details[0]  = "connecting..."
        update_log()

        from agents.ingestion import ingest
        articles = ingest(interests=profile.interests)

        if not articles:
            statuses[0] = "error"
            details[0]  = "no articles returned"
            update_log()
            st.session_state.pipeline_running = False
            st.error("Could not fetch articles. Check API keys or internet connection.")
            if st.button("← Back to profile"):
                st.session_state.step = "profile"
                st.rerun()
            return

        statuses[0] = "done"
        details[0]  = f"{len(articles)} articles fetched"
        update_log()

        # ── Stage 1: Understanding ──────────────────────────────────────────
        statuses[1] = "running"
        details[1]  = f"analyzing {len(articles)} articles..."
        update_log()

        from agents.understanding import understand
        analyzed = understand(articles)

        statuses[1] = "done"
        details[1]  = f"{len(analyzed)} articles analyzed"
        update_log()

        # ── Stage 2: Profiling ──────────────────────────────────────────────
        statuses[2] = "running"
        details[2]  = "interpreting preferences..."
        update_log()

        from agents.profiling import interpret_profile
        profile_data = interpret_profile(profile)

        statuses[2] = "done"
        details[2]  = "profile expanded"
        update_log()

        # ── Stage 3: Personalization ────────────────────────────────────────
        statuses[3] = "running"
        details[3]  = f"scoring {len(analyzed)} articles..."
        update_log()

        from agents.personalization import personalize
        ranked = personalize(analyzed, profile, profile_data)

        statuses[3] = "done"
        details[3]  = f"top {min(3, len(ranked))} selected"
        update_log()

        # ── Stage 4: Briefing ───────────────────────────────────────────────
        statuses[4] = "running"
        details[4]  = "generating briefing text..."
        update_log()

        from agents.briefing import generate_briefing
        briefing = generate_briefing(ranked, profile, profile_data)

        statuses[4] = "done"
        details[4]  = "ready"
        update_log()

        # ── TTS (not a named pipeline stage) ───────────────────────────────
        from agents.voice import text_to_speech
        audio_bytes = text_to_speech(briefing.summary_text)

        st.session_state.briefing       = briefing
        st.session_state.briefing_audio = audio_bytes
        st.session_state.pipeline_running = False
        st.session_state.step           = "briefing"
        st.rerun()

    except Exception as e:
        # Mark the current running stage as error
        for i, s in enumerate(statuses):
            if s == "running":
                statuses[i] = "error"
                details[i]  = str(e)[:40]
        update_log()
        st.session_state.pipeline_running = False
        st.error(f"Pipeline error: {e}")
        if st.button("← Back to profile"):
            st.session_state.step = "profile"
            st.rerun()


# =============================================================================
# BRIEFING PAGE
# =============================================================================

def _sentiment_class(sentiment: str) -> str:
    """Map sentiment string to CSS class for left-border color."""
    mapping = {
        "positive": "sentiment-positive",
        "negative": "sentiment-negative",
    }
    return mapping.get(sentiment.lower(), "sentiment-neutral")


def _relevance_badge(score: float) -> str:
    """Return HTML for the relevance badge based on score."""
    if score >= 0.7:
        return f'<span class="relevance-badge badge-high">{score:.0%} match</span>'
    elif score >= 0.4:
        return f'<span class="relevance-badge badge-med">{score:.0%} match</span>'
    else:
        return f'<span class="relevance-badge badge-low">{score:.0%} match</span>'


def render_article_card(idx: int, article) -> None:
    """
    Render a single article card with:
    - Sentiment-coded left border (green/grey/red — no emoji icons)
    - H3-weight title via .article-title
    - Small/muted metadata row (source, date, topics) — nothing in between
    - Relevance badge using color-coded pill
    - 'Why it matters' in italic below a hairline rule
    """
    sentiment_class = _sentiment_class(article.sentiment)
    badge_html      = _relevance_badge(article.relevance_score)

    # Truncate description to avoid wall-of-text
    description = (article.description[:220] + "…") if len(article.description) > 220 else article.description

    # Published date — shorten to date only if it contains a T (ISO format)
    pub_date = article.published_at.split("T")[0] if "T" in article.published_at else article.published_at

    topics_str = " · ".join(article.topics[:4]) if article.topics else ""

    st.markdown(f"""
    <div class="article-card {sentiment_class}">
        <h3 class="article-title">{idx}. {article.title}</h3>
        <div class="article-meta">
            {badge_html}
            <span class="article-source">{article.source}</span>
            {'<span class="article-date">' + pub_date + '</span>' if pub_date else ''}
            {'<span class="article-topics">' + topics_str + '</span>' if topics_str else ''}
        </div>
        <p class="article-body">{description}</p>
        {'<p class="article-insight">' + article.why_it_matters + '</p>' if article.why_it_matters else ''}
    </div>
    """, unsafe_allow_html=True)


def render_chat_thread() -> None:
    """
    Render the full chat history as a message thread.
    User bubbles are right-aligned; AI bubbles left-aligned.
    Always fully visible — no collapse, no hover-to-reveal.
    """
    history = st.session_state.chat_history

    if not history:
        thread_inner = '<div class="chat-empty">No messages yet. Ask a question below.</div>'
    else:
        bubbles = ""
        for msg in history:
            if msg["role"] == "user":
                bubbles += f"""
                <div class="chat-bubble chat-bubble-user">
                    <div class="bubble-label">You</div>
                    {msg['content']}
                </div>"""
            else:
                bubbles += f"""
                <div class="chat-bubble chat-bubble-ai">
                    <div class="bubble-label">MyET AI</div>
                    {msg['content']}
                </div>"""
        thread_inner = bubbles

    st.markdown(f'<div class="chat-thread">{thread_inner}</div>', unsafe_allow_html=True)


# =============================================================================
# CALLING UI HELPERS
# =============================================================================

def _handle_call_now(phone: str, briefing, profile) -> None:
    """
    Validate the phone number and immediately place a Twilio outbound call.

    On success: creates a ScheduledCall record with status="calling" and
    stores it in shared_state so the status list updates.
    On failure: shows an error in the UI — never raises.

    Args:
        phone:    E.164-format phone number from the UI text input.
        briefing: Current Briefing object (summary_text injected into Tony).
        profile:  UserProfile for ElevenLabs context priming.
    """
    from agents.twilio_caller import initiate_call
    from config import TWILIO_ACCOUNT_SID

    # Basic validation before attempting any API call
    if not phone.strip():
        st.warning("Enter a phone number in E.164 format, e.g. +919876543210.")
        return
    if not TWILIO_ACCOUNT_SID:
        st.error(
            "Twilio not configured. Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "and TWILIO_FROM_NUMBER to your .env file."
        )
        return

    with st.spinner("Placing call…"):
        try:
            # initiate_call() primes ElevenLabs then dials via Twilio
            call_sid = initiate_call(phone.strip(), briefing, profile)

            # Record the call in shared state so the status list shows it
            new_call = ScheduledCall(
                phone_number=phone.strip(),
                scheduled_at=datetime.now(timezone.utc),
                status="calling",
                call_sid=call_sid,
            )
            with calls_lock:
                scheduled_calls[new_call.id] = new_call

            st.success(f"Call placed! CallSid: {call_sid}")
        except RuntimeError as exc:
            st.error(f"Call failed: {exc}")


def _render_schedule_form(phone: str, briefing, profile) -> None:
    """
    Render date + time pickers and a Schedule button inside an st.expander.

    On submit: converts the IST time to UTC, creates a ScheduledCall record,
    and registers an APScheduler 'date' job to fire initiate_call() at that time.

    Args:
        phone:    E.164-format phone number from the UI text input (shared with _handle_call_now).
        briefing: Briefing to deliver — captured in the job closure at schedule time.
        profile:  UserProfile — also captured in the job closure.
    """
    from scheduler import get_scheduler

    # Date and time pickers — shown in IST for the user's convenience
    sched_date = st.date_input("Call date", key="sched_date")
    sched_time = st.time_input("Call time (IST)", key="sched_time")

    if st.button("Schedule", key="schedule_btn"):
        if not phone.strip():
            st.warning("Enter a phone number before scheduling.")
            return

        # Convert IST → UTC for APScheduler
        # ZoneInfo("Asia/Kolkata") is stdlib (Python 3.9+) — no pytz needed
        ist = ZoneInfo("Asia/Kolkata")
        naive_local = datetime.combine(sched_date, sched_time)
        aware_ist   = naive_local.replace(tzinfo=ist)
        utc_dt      = aware_ist.astimezone(timezone.utc)

        if utc_dt <= datetime.now(timezone.utc):
            st.warning("Scheduled time must be in the future.")
            return

        # Create the record BEFORE registering the job so we have an ID
        new_call = ScheduledCall(
            phone_number=phone.strip(),
            scheduled_at=utc_dt,
            status="scheduled",
        )
        with calls_lock:
            scheduled_calls[new_call.id] = new_call

        # Capture briefing/profile/phone by value in the closure.
        # APScheduler runs this in a thread pool worker at utc_dt.
        # Pydantic v2 models are immutable by default — closures are safe.
        def _job(call_id=new_call.id, ph=phone.strip(), br=briefing, pr=profile):
            """APScheduler job: update status → placing call → store SID."""
            from agents.twilio_caller import initiate_call as _initiate
            # Mark as "calling" before dialling so the UI reflects the attempt
            with calls_lock:
                call = scheduled_calls.get(call_id)
                if call:
                    call.status = "calling"
            try:
                sid = _initiate(ph, br, pr)
                with calls_lock:
                    call = scheduled_calls.get(call_id)
                    if call:
                        call.call_sid = sid
            except Exception as exc:
                # Mark as failed if Twilio raises; Twilio webhook handles completed/failed
                with calls_lock:
                    call = scheduled_calls.get(call_id)
                    if call:
                        call.status = "failed"
                print(f"[Scheduler] Job failed for {call_id}: {exc}")

        scheduler = get_scheduler()
        # 'date' trigger fires the job exactly once at run_date (UTC)
        scheduler.add_job(_job, "date", run_date=utc_dt, id=new_call.id)

        ist_str = aware_ist.strftime("%d %b %Y at %I:%M %p IST")
        st.success(f"Call scheduled for {ist_str}.")


def _render_scheduled_calls_list() -> None:
    """
    Display all ScheduledCall records with colour-coded status badges.

    Reads from shared_state.scheduled_calls (thread-safe snapshot under lock).
    Sorted by created_at descending (most recent first).

    Status badge colours:
        scheduled / calling → amber  #c8a96e  (matches editorial accent colour)
        completed           → green  #4caf50
        failed              → red    #ef5350
    """
    with calls_lock:
        # Take a snapshot so we don't hold the lock while rendering HTML
        calls_snapshot = list(scheduled_calls.values())

    if not calls_snapshot:
        return  # Nothing to show yet — skip the section entirely

    st.markdown('<div class="section-label">Scheduled calls</div>', unsafe_allow_html=True)

    # Sort most-recent first for a natural chronological display
    for call in sorted(calls_snapshot, key=lambda c: c.created_at, reverse=True):
        badge_color = {
            "scheduled": "#c8a96e",
            "calling":   "#c8a96e",
            "completed": "#4caf50",
            "failed":    "#ef5350",
        }.get(call.status, "#4a4440")

        # Format the UTC datetime for display
        scheduled_str = call.scheduled_at.strftime("%d %b %Y %H:%M UTC")

        st.markdown(f"""
        <div style="background:#141414;border:1px solid #2a2a2a;border-radius:6px;
                    padding:12px 16px;margin:6px 0;display:flex;align-items:center;gap:12px;">
            <span style="font-family:'IBM Plex Mono',monospace;font-size:0.68rem;
                         color:{badge_color};text-transform:uppercase;letter-spacing:0.08em;
                         border:1px solid {badge_color};padding:1px 8px;border-radius:6px;">
                {call.status}
            </span>
            <span style="font-family:'IBM Plex Mono',monospace;font-size:0.8rem;color:#e8e0d0;">
                {call.phone_number}
            </span>
            <span style="font-family:'IBM Plex Mono',monospace;font-size:0.68rem;color:#4a4440;
                         margin-left:auto;">
                {scheduled_str}
            </span>
        </div>
        """, unsafe_allow_html=True)


def render_briefing_page():
    """Step 3: Briefing audio player, article cards, and conversational Q&A thread."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    briefing = st.session_state.briefing
    profile  = st.session_state.profile

    # ── Page header ─────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="padding: 28px 0 4px 0;">
        <p class="page-title">Your Briefing</p>
        <p class="page-subtitle">{profile.name} &mdash; {profile.role}</p>
    </div>
    """, unsafe_allow_html=True)

    # Transcript in expander — secondary to audio
    with st.expander("Read transcript", expanded=False):
        st.markdown(f'<p style="font-family:\'Source Serif 4\',serif;font-size:0.92rem;color:#b0a898;line-height:1.7;">{briefing.summary_text}</p>', unsafe_allow_html=True)

    # ── Article cards ────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Top stories</div>', unsafe_allow_html=True)
    for i, article in enumerate(briefing.top_articles, 1):
        render_article_card(i, article)

    # ── Phone calling section ─────────────────────────────────────────────────
    # Tony (ElevenLabs) handles the live call — same agent as in-browser Q&A.
    # "Call Me Now" places an immediate call; "Schedule a call" books a future one.
    st.markdown('<div class="section-label">Get called by Tony</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="font-family:\'Source Serif 4\',serif;font-style:italic;'
        'font-size:0.82rem;color:#4a4440;margin-bottom:10px;">'
        'Tony will call you and deliver this briefing over the phone.</p>',
        unsafe_allow_html=True,
    )

    col_phone, col_actions = st.columns([2, 1])

    with col_phone:
        # Phone input persists across reruns so user doesn't retype after scheduling
        phone_input = st.text_input(
            "Phone number",
            value=st.session_state.get("call_phone_number", ""),
            placeholder="+919876543210",
            label_visibility="collapsed",
            key="phone_input_field",
        )
        st.session_state.call_phone_number = phone_input

    with col_actions:
        if st.button("Call Me Now", type="primary", use_container_width=True, key="call_now_btn"):
            _handle_call_now(phone_input, briefing, profile)

        with st.expander("Schedule a call", expanded=False):
            _render_schedule_form(phone_input, briefing, profile)

    # Live status list — reads from shared_state; updates on next Streamlit rerun
    _render_scheduled_calls_list()

    # ── Q&A section ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-label">Ask a follow-up</div>', unsafe_allow_html=True)
    st.markdown('<p style="font-family:\'Source Serif 4\',serif;font-style:italic;font-size:0.82rem;color:#4a4440;margin-bottom:10px;">Ask about any story, request context, or explore a topic further.</p>', unsafe_allow_html=True)

    render_chat_thread()

    # ── Q&A text input (voice recording removed — replaced by phone calls) ──────
    st.text_input("Question", key="chat_input",
                  placeholder="e.g., Why does this matter for Indian markets?",
                  label_visibility="collapsed")
    if st.button("Send", key="send_btn", type="primary"):
        question = st.session_state.get("chat_input", "").strip()
        if question:
            process_user_question(question)

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown('<p style="font-family:\'IBM Plex Mono\',monospace;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.1em;color:#4a4440;margin-bottom:14px;">Controls</p>', unsafe_allow_html=True)
        if st.button("New briefing", use_container_width=True):
            st.session_state.step           = "profile"
            st.session_state.briefing       = None
            st.session_state.chat_history   = []
            st.session_state.briefing_audio = None
            st.rerun()

        st.markdown('<hr/>', unsafe_allow_html=True)
        st.markdown("""
        <p style="font-family:'IBM Plex Mono',monospace;font-size:0.65rem;color:#4a4440;line-height:1.8;">
        MyET AI + Voice Companion<br>
        Multi-agent news intelligence<br><br>
        ET AI Hackathon — Track 8
        </p>
        """, unsafe_allow_html=True)


# =============================================================================
# Q&A HANDLER
# =============================================================================

def process_user_question(question: str):
    """
    Process a typed follow-up question about the briefing via Gemini.

    Voice recording has been removed — all Q&A is text input only.
    Answers via agents/conversation.py (Gemini) + gTTS for audio playback.

    Args:
        question: The user's typed question string.
    """
    briefing = st.session_state.briefing
    profile  = st.session_state.profile

    # Snapshot history BEFORE appending current question.
    # answer_question() adds "User's question: {question}" separately,
    # so passing the post-append history would double-count the question.
    history_snapshot = list(st.session_state.chat_history)
    st.session_state.chat_history.append({"role": "user", "content": question})

    from agents.conversation import answer_question
    from agents.voice import text_to_speech

    try:
        response = answer_question(
            question=question,
            briefing=briefing,
            profile=profile,
            chat_history=history_snapshot,
        )
    except Exception as exc:
        response = f"Unable to process your question. ({exc})"

    st.session_state.chat_history.append({"role": "assistant", "content": response})

    try:
        st.session_state.last_response_audio = text_to_speech(response)
    except Exception:
        st.session_state.last_response_audio = None

    st.rerun()


# =============================================================================
# MAIN
# =============================================================================

def main():
    init_session_state()

    # ── One-time background service startup ───────────────────────────────────
    # Both start_server() and get_scheduler() are guarded internally against
    # double-starting on Streamlit reruns (module-level flags + threading.Lock).
    from server import start_server
    from scheduler import get_scheduler
    start_server()    # FastAPI on :8000 — receives Twilio status callbacks
    get_scheduler()   # APScheduler — fires scheduled call jobs in background thread

    if st.session_state.step == "profile":
        render_profile_page()
    elif st.session_state.step == "loading":
        render_loading_page()
    elif st.session_state.step == "briefing":
        render_briefing_page()
        # Auto-play last Q&A response audio at page bottom
        if st.session_state.get("last_response_audio"):
            st.audio(st.session_state.last_response_audio, format="audio/mp3")
            st.session_state.last_response_audio = None


if __name__ == "__main__":
    main()
