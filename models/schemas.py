"""Data models for the pipeline."""
from pydantic import BaseModel
from typing import Optional


class UserProfile(BaseModel):
    """User profile collected at session start."""
    name: str = ""
    role: str = ""  # e.g., "investor", "student", "professional", "entrepreneur"
    interests: list[str] = []  # e.g., ["technology", "markets", "startups"]
    preferred_depth: str = "medium"  # "brief", "medium", "detailed"
    preferred_language: str = "english"


class Article(BaseModel):
    """Raw article from news source."""
    title: str
    description: str = ""
    content: str = ""
    source: str = ""
    url: str = ""
    published_at: str = ""
    image_url: str = ""


class AnalyzedArticle(BaseModel):
    """Article after understanding agent processes it."""
    title: str
    description: str = ""
    content: str = ""
    source: str = ""
    url: str = ""
    published_at: str = ""
    image_url: str = ""
    topics: list[str] = []
    entities: list[str] = []
    sentiment: str = ""  # "positive", "negative", "neutral"
    relevance_score: float = 0.0  # 0-1, set by personalization agent
    why_it_matters: str = ""  # set by briefing agent


class Briefing(BaseModel):
    """Final briefing output."""
    greeting: str = ""
    top_articles: list[AnalyzedArticle] = []
    summary_text: str = ""  # Full text for TTS
    generated_at: str = ""
