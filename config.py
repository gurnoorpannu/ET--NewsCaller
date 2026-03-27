"""Configuration and API keys."""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys — replace with real keys or set in .env
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "YOUR_NEWSAPI_KEY_HERE")

# Gemini model config
GEMINI_MODEL = "gemini-2.0-flash"

# News settings
MAX_ARTICLES = 20
DEFAULT_COUNTRY = "in"  # India for ET
