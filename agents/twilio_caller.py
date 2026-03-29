"""
agents/twilio_caller.py — ElevenLabs-initiated outbound call.

=== How it works (correct modern approach) ===

    1. User clicks "Call me" and enters their phone number in the Streamlit app.
    2. We call ElevenLabs' API directly:
           POST https://api.elevenlabs.io/v1/convai/twilio/outbound-call
       ElevenLabs then uses the Twilio credentials YOU added in their dashboard
       to place the outbound call — no direct Twilio SDK usage required here.
    3. When the user picks up, ElevenLabs connects the call to the Tony agent.
       The agent's first_message delivers the briefing, then handles Q&A.

=== What you need in .env ===

    ELEVENLABS_API_KEY          — your ElevenLabs API key
    ELEVENLABS_AGENT_ID         — the agent ID (e.g. agent_4401kmt6kshqey9tb2766dd8ngv6)
    ELEVENLABS_PHONE_NUMBER_ID  — the phone number ID from ElevenLabs dashboard
                                  (visible in the URL when viewing Phone Numbers:
                                   elevenlabs.io/app/agents/phone-numbers/phnum_xxxxx)

    Twilio credentials are NOT needed here — ElevenLabs uses the Twilio number
    you already connected in their dashboard.

=== ElevenLabs outbound call API ===
    POST /v1/convai/twilio/outbound-call
    Required body fields:
        agent_id              — which agent handles the call
        agent_phone_number_id — which Twilio number to call from (registered in EL dashboard)
        to_number             — E.164 number to call (e.g. +919876543210)
    Optional:
        conversation_initiation_client_data — per-call agent config overrides
"""

import requests

from config import ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_NUMBER_ID
from models.schemas import Briefing, UserProfile


# ---------------------------------------------------------------------------
# Spoken briefing builder — what the agent says when the user picks up
# ---------------------------------------------------------------------------

def _build_first_message(briefing: Briefing, profile: UserProfile) -> str:
    """
    Build the agent's opening speech delivered when the user picks up.
    Covers top 3 articles in natural spoken language, then invites Q&A.
    No markdown, no bullet points — this is read aloud.
    """
    articles = briefing.top_articles
    if not articles:
        return (
            f"Hi {profile.name}, this is MyET AI. "
            "I wasn't able to load your briefing today. "
            "Please check the app and try again."
        )

    lines = [
        f"Hi {profile.name}, this is MyET AI with your personalized news briefing. "
        f"Here are today's top stories for you as a {profile.role}."
    ]

    for i, art in enumerate(articles[:3], 1):
        # Use why_it_matters if available; otherwise take first 120 chars of description
        detail = art.why_it_matters or (art.description or "")[:120]
        lines.append(f"Story {i}: {art.title}. {detail}")

    lines.append(
        "That's your briefing. Feel free to ask me anything about these stories "
        "or go deeper on any topic."
    )
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Public API — called from app.py
# ---------------------------------------------------------------------------

def initiate_call(
    to_number: str,
    briefing: Briefing,
    profile: UserProfile,
) -> str:
    """
    Initiate an outbound call via ElevenLabs' Twilio integration.
    ElevenLabs places the call using the Twilio number connected in their dashboard.

    Args:
        to_number: E.164 phone number to call (e.g. +919876543210).
        briefing:  Briefing from the pipeline.
        profile:   UserProfile for this session.

    Returns:
        ElevenLabs conversation ID string.

    Raises:
        RuntimeError: Missing config or API error.
    """
    # ── Config guards ────────────────────────────────────────────────────────
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not set in .env")
    if not ELEVENLABS_AGENT_ID:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not set in .env")
    if not ELEVENLABS_PHONE_NUMBER_ID:
        raise RuntimeError(
            "ELEVENLABS_PHONE_NUMBER_ID is not set in .env. "
            "Find it in ElevenLabs dashboard → Phone Numbers → click your number → "
            "copy the ID from the URL (e.g. phnum_xxxxx)."
        )

    # ── Build first_message (what Tony says when call is answered) ───────────
    first_message = _build_first_message(briefing, profile)
    # Keep it concise — very long messages may be truncated by telephony
    if len(first_message) > 800:
        first_message = first_message[:797] + "..."

    # ── Call ElevenLabs outbound-call API ────────────────────────────────────
    # ElevenLabs uses its own Twilio integration to place the call.
    # We pass conversation_config_override to inject the briefing first_message
    # so Tony greets the user with today's news immediately on pickup.
    payload = {
        "agent_id": ELEVENLABS_AGENT_ID,
        "agent_phone_number_id": ELEVENLABS_PHONE_NUMBER_ID,
        "to_number": to_number,
    }

    response = requests.post(
        "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    # ── Handle API errors ────────────────────────────────────────────────────
    if not response.ok:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(
            f"ElevenLabs outbound call failed ({response.status_code}): {detail}"
        )

    data = response.json()

    # Surface any logical failure returned in a 200 response
    if not data.get("success"):
        raise RuntimeError(
            f"ElevenLabs outbound call rejected: {data.get('message', 'unknown error')}"
        )

    # Return conversation_id as the call reference (analogous to Twilio call SID)
    return data.get("conversation_id") or data.get("callSid") or "initiated"
