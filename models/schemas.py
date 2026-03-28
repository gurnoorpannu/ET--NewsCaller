"""Data models for the pipeline."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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


class ScheduledCall(BaseModel):
    """
    Tracks one outbound phone call — immediate or scheduled.

    Status lifecycle:
        "scheduled"  — APScheduler job registered, call not yet placed
        "calling"    — Twilio call initiated, in progress
        "completed"  — Twilio reported CallStatus == "completed"
        "failed"     — Twilio reported failure (failed / busy / no-answer / canceled)
    """
    # Unique identifier — used as the APScheduler job ID too
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Destination phone number in E.164 format, e.g. "+919876543210"
    phone_number: str
    # UTC datetime when the call should fire (or was fired for immediate calls)
    scheduled_at: datetime
    # Current status — one of the four states above
    status: str = "scheduled"
    # Twilio CallSid — set after Twilio confirms the call was placed
    call_sid: Optional[str] = None
    # UTC datetime this record was created (for display sorting)
    created_at: datetime = Field(default_factory=datetime.utcnow)
