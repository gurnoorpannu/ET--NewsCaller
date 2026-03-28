"""
agents/twilio_caller.py — Twilio outbound call + ElevenLabs native integration.

Call flow:
    1. POST conversation_initiation_client_data to ElevenLabs REST API.
       Seeds Tony with the user's briefing summary and profile before the
       call connects — so he greets them with their personalized briefing.
    2. Twilio.calls.create() places the outbound call.
       The `url` parameter points Twilio to the ElevenLabs Twilio webhook.
       ElevenLabs returns <Connect><Stream> TwiML directing Twilio to its
       WebSocket — no intermediary server needed in this repo.
    3. status_callback receives Twilio POSTs as call status changes.
       Handled in server.py, updates shared_state.scheduled_calls.

ElevenLabs Twilio webhook URL pattern:
    https://api.elevenlabs.io/v1/convai/twilio?agent_id={ELEVENLABS_AGENT_ID}
"""

import requests

from config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_AGENT_ID,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    WEBHOOK_BASE_URL,
)
from models.schemas import Briefing, UserProfile


# ---------------------------------------------------------------------------
# Internal helper — ElevenLabs context priming
# ---------------------------------------------------------------------------

def _prime_elevenlabs_context(briefing: Briefing, profile: UserProfile) -> None:
    """
    Pre-seed ElevenLabs Tony with the user's briefing before the call connects.

    POSTs conversation_initiation_client_data to the ElevenLabs REST API so
    Tony has the briefing summary and user context the moment the call picks up.

    This is best-effort: if the POST fails, Tony still answers the call using
    his default persona — he just won't know the briefing content in advance.
    Failure is logged but never raised so a network hiccup cannot block a call.

    ElevenLabs API endpoint:
        POST https://api.elevenlabs.io/v1/convai/conversation/initiation/client-data

    Headers follow the same pattern as agents/elevenlabs_convo.py:
        xi-api-key: <ELEVENLABS_API_KEY>
    """
    if not ELEVENLABS_API_KEY or not ELEVENLABS_AGENT_ID:
        # Keys not configured — skip silently rather than raising
        print("[TwilioCaller] ElevenLabs keys not set — skipping context priming.")
        return

    # Build a concise context string that Tony will use as his opening prompt.
    # Same format as the context built in agents/elevenlabs_convo.py.
    context = (
        f"You are Tony, a personal AI news companion. "
        f"You are calling {profile.name} ({profile.role}) to deliver their "
        f"personalized news briefing. Here is today's briefing:\n\n"
        f"{briefing.summary_text}\n\n"
        f"Greet them warmly, summarise the top stories, and answer any "
        f"follow-up questions they have about these stories."
    )

    # Override the agent's system prompt for this single conversation only.
    # The outer key structure is required by the ElevenLabs convai API.
    payload = {
        "agent_id": ELEVENLABS_AGENT_ID,
        "conversation_config_override": {
            "agent": {
                "prompt": {
                    "prompt": context
                }
            }
        },
    }

    # xi-api-key is the ElevenLabs authentication header — same as in elevenlabs_convo.py
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            "https://api.elevenlabs.io/v1/convai/conversation/initiation/client-data",
            json=payload,
            headers=headers,
            timeout=10,  # 10s ceiling — don't delay a call for a slow network
        )
        if resp.status_code not in (200, 201):
            # Log the failure but don't block the call
            print(
                f"[TwilioCaller] ElevenLabs context prime failed: "
                f"{resp.status_code} {resp.text[:200]}"
            )
    except requests.RequestException as exc:
        # Network error, DNS failure, timeout — all are best-effort, never fatal
        print(f"[TwilioCaller] ElevenLabs context prime request error: {exc}")


# ---------------------------------------------------------------------------
# Public API — called from the APScheduler job in app.py / scheduler.py
# ---------------------------------------------------------------------------

def initiate_call(phone_number: str, briefing: Briefing, profile: UserProfile) -> str:
    """
    Place an outbound call via Twilio, connected to ElevenLabs Tony.

    Flow:
        1. Validates that all three Twilio config vars are set.
        2. Calls _prime_elevenlabs_context() (best-effort).
        3. Calls twilio.Client.calls.create() with:
           - url  = ElevenLabs' Twilio webhook (returns TwiML for the call)
           - status_callback = our FastAPI /twilio/status endpoint

    Args:
        phone_number:  Destination in E.164 format, e.g. "+919876543210".
        briefing:      Briefing from the pipeline — summary_text is injected.
        profile:       UserProfile for the context priming message.

    Returns:
        Twilio CallSid string (e.g. "CAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx").

    Raises:
        RuntimeError: If any required Twilio config var is missing, or if
                      the Twilio SDK is not installed, or if the Twilio API
                      returns an error.
    """
    # Guard: all three Twilio vars must be set before attempting a call.
    # Missing keys are reported together so the user can fix them all at once.
    missing = [
        k for k, v in {
            "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
            "TWILIO_AUTH_TOKEN":  TWILIO_AUTH_TOKEN,
            "TWILIO_FROM_NUMBER": TWILIO_FROM_NUMBER,
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(f"Missing Twilio config: {', '.join(missing)}")

    # Pre-seed Tony with the briefing context (best-effort, does not raise).
    # Tony will still answer if this step fails — he just won't have context.
    _prime_elevenlabs_context(briefing, profile)

    # Lazy import so the app still starts if twilio is not yet installed.
    # Users without the package see a clear install instruction rather than
    # an ImportError at module load time.
    try:
        from twilio.rest import Client
    except ImportError:
        raise RuntimeError(
            "twilio package not installed. Run: pip install twilio"
        )

    # ElevenLabs native Twilio integration endpoint.
    # Twilio fetches TwiML from this URL when the call connects.
    # ElevenLabs returns <Connect><Stream> pointing to its own WebSocket,
    # so Twilio streams audio bidirectionally to the ElevenLabs Tony agent.
    elevenlabs_twiml_url = (
        f"https://api.elevenlabs.io/v1/convai/twilio"
        f"?agent_id={ELEVENLABS_AGENT_ID}"
    )

    # Our FastAPI webhook receives Twilio status POSTs here.
    # Twilio sends: CallSid, CallStatus (initiated → ringing → in-progress → completed/failed)
    status_callback_url = f"{WEBHOOK_BASE_URL}/twilio/status"

    # Instantiate Twilio REST client with credentials from config.py / .env
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    try:
        call = client.calls.create(
            to=phone_number,
            from_=TWILIO_FROM_NUMBER,
            url=elevenlabs_twiml_url,           # Twilio fetches TwiML from ElevenLabs
            status_callback=status_callback_url,
            status_callback_method="POST",
            # Only subscribe to terminal events to reduce webhook noise.
            # Twilio will POST to status_callback_url when one of these fires.
            status_callback_event=["completed", "failed", "busy", "no-answer", "canceled"],
        )
    except Exception as exc:
        raise RuntimeError(f"Twilio API error: {exc}") from exc

    print(f"[TwilioCaller] Call placed: {call.sid} → {phone_number}")
    return call.sid
