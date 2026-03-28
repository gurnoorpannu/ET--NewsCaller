"""Configuration and API keys."""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys — replace with real keys or set in .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "YOUR_NEWSAPI_KEY_HERE")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "")

# Twilio credentials — required for outbound calling
TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "")

# Public base URL for FastAPI webhook (Twilio posts status callbacks here).
# Local dev: run `ngrok http 8000` and set this to the HTTPS ngrok URL.
WEBHOOK_BASE_URL    = os.getenv("WEBHOOK_BASE_URL", "http://localhost:8000")

# Gemini model config
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# News settings (default 3 for faster local testing; set MAX_ARTICLES in .env for demos/prod)
MAX_ARTICLES = max(1, int(os.getenv("MAX_ARTICLES", "3")))
DEFAULT_COUNTRY = "in"  # India for ET
