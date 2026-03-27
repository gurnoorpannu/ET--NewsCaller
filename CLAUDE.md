# MyET AI + Voice Companion

## What This Is

A multi-agent AI system that delivers personalized, voice-interactive news briefings. Built for the ET AI Hackathon (Track 8: AI-Native News Experience).

The core idea: **News should adapt to the user, not the other way around.**

Instead of a static news feed, this system ingests articles, understands them deeply, personalizes them to the user's profile, generates a conversational briefing, and delivers it via voice — with real-time Q&A.

---

## Architecture

This is a **7-agent pipeline**, not a single LLM call. Each agent has a single responsibility and passes structured data to the next.

### Pipeline Flow

```
User Profile → [Ingestion] → [Understanding] → [Profiling] → [Personalization] → [Briefing] → [Voice] → [Conversation]
```

### Agent Breakdown

| # | Agent | File | Responsibility |
|---|-------|------|----------------|
| 1 | Ingestion Agent | `agents/ingestion.py` | Fetches articles from NewsAPI + ET RSS feeds. Falls back to RSS if NewsAPI key is missing. Deduplicates by title. |
| 2 | Understanding Agent | `agents/understanding.py` | Sends each article to Gemini to extract: topics (list), entities (people/companies/places), sentiment (positive/negative/neutral). Returns `AnalyzedArticle` objects. |
| 3 | Profiling Agent | `agents/profiling.py` | Takes the raw `UserProfile` and asks Gemini to expand it into actionable preferences: priority topics, communication tone, focus areas, topics to avoid. |
| 4 | Personalization Agent | `agents/personalization.py` | Scores every article 0.0–1.0 for relevance to THIS user (via Gemini). Sorts by score descending. |
| 5 | Briefing Agent | `agents/briefing.py` | Takes the top 3 ranked articles and generates a natural, conversational briefing text (designed to be read aloud). Also generates per-article "why it matters" explanations. |
| 6 | Voice Agent | `agents/voice.py` | TTS: converts briefing text → MP3 audio via gTTS. STT: converts user's voice input → text via Google SpeechRecognition. |
| 7 | Conversation Agent | `agents/conversation.py` | Handles follow-up Q&A. Receives the full briefing as context + chat history, answers user questions conversationally. Responses are also converted to voice. |

### Pipeline Orchestrator

`pipeline.py` — connects agents 1–5 in sequence. Voice and Conversation agents are called on-demand from the UI.

---

## Data Models

Defined in `models/schemas.py` using Pydantic:

- **`UserProfile`** — name, role (e.g. "Investor"), interests (list), preferred_depth (brief/medium/detailed)
- **`Article`** — raw article: title, description, content, source, url, published_at, image_url
- **`AnalyzedArticle`** — extends Article with: topics, entities, sentiment, relevance_score, why_it_matters
- **`Briefing`** — final output: greeting, top_articles (list of AnalyzedArticle), summary_text (for TTS), generated_at

---

## Tech Stack

| Layer | Tool | Notes |
|-------|------|-------|
| LLM | Google Gemini (gemini-2.0-flash) | Free tier. Wrapper in `utils/llm.py` |
| News Source | NewsAPI + RSS (Economic Times) | RSS is the free fallback |
| Text-to-Speech | gTTS | Free, no API key |
| Speech-to-Text | Google SpeechRecognition | Free, no API key |
| Frontend | Streamlit | Single-page app with 3 screens |
| Data Models | Pydantic v2 | Strict typing throughout |

---

## UI Flow (app.py)

The Streamlit app has 3 screens controlled by `st.session_state.step`:

1. **`profile`** — Form: name, role (dropdown), interests (multiselect), depth (slider). Submitting creates a `UserProfile` and triggers the pipeline.
2. **`loading`** — Runs the pipeline with a progress bar showing each agent's stage. Generates TTS audio at the end.
3. **`briefing`** — Displays:
   - Audio player (full briefing as MP3)
   - Expandable text transcript
   - Article cards with relevance badges, source, topics, sentiment, "why it matters"
   - Q&A section: mic button (audio-recorder-streamlit) + text input → AI responds → response also plays as audio

---

## Configuration

`config.py` reads from environment variables (`.env` file):

- `GEMINI_API_KEY` — required for all LLM calls
- `NEWS_API_KEY` — optional, system falls back to RSS feeds without it
- `GEMINI_MODEL` — defaults to `gemini-2.0-flash`
- `MAX_ARTICLES` — defaults to 20
- `DEFAULT_COUNTRY` — defaults to `in` (India)

---

## How to Run

```bash
cp .env.example .env
# Add your GEMINI_API_KEY (required) and NEWS_API_KEY (optional) to .env
pip install -r requirements.txt
streamlit run app.py
```

---

## Key Design Decisions

- **Multi-agent over monolithic**: Each agent is a separate module with a clear input/output contract. This makes the system explainable and demo-able (you can show each agent's contribution).
- **RSS fallback**: The system works even without a NewsAPI key — ET RSS feeds provide real Indian business/tech news.
- **Voice-first design**: The briefing text is written for spoken delivery (no markdown, no bullet points). The UI is built around audio playback.
- **Session-only profiles**: No database. Profile lives in Streamlit session state. Keeps the MVP simple.
- **Gemini for everything**: Understanding, profiling, personalization, briefing, and Q&A all use the same Gemini model via `utils/llm.py`. Two functions: `ask_llm()` for free-text and `ask_llm_json()` for structured responses.

---

## File Map

```
Et-hack/
├── app.py                  # Streamlit UI — the main entry point
├── config.py               # API keys and settings
├── pipeline.py             # Orchestrates agents 1–5 in sequence
├── requirements.txt        # Python dependencies
├── .env.example            # Template for API keys
├── .gitignore
├── models/
│   ├── __init__.py
│   └── schemas.py          # Pydantic models: UserProfile, Article, AnalyzedArticle, Briefing
├── agents/
│   ├── __init__.py
│   ├── ingestion.py        # Agent 1: NewsAPI + RSS fetching
│   ├── understanding.py    # Agent 2: Topic/entity/sentiment extraction
│   ├── profiling.py        # Agent 3: User profile interpretation
│   ├── personalization.py  # Agent 4: Article relevance scoring
│   ├── briefing.py         # Agent 5: Conversational briefing generation
│   ├── voice.py            # Agent 6: TTS (gTTS) + STT (SpeechRecognition)
│   └── conversation.py     # Agent 7: Follow-up Q&A
└── utils/
    ├── __init__.py
    └── llm.py              # Gemini API wrapper
```
