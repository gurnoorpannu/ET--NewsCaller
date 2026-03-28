"""
server.py — FastAPI webhook server for Twilio call status callbacks.

Runs in a background daemon thread alongside Streamlit (same Python process).
Listens on port 8000.

Why a separate thread (not a separate process)?
    Streamlit and this server must share `scheduled_calls` from shared_state.py.
    Python's threading model makes this trivial — the dict is shared by reference.
    A separate process (e.g. subprocess or multiprocessing) would need IPC.
    The GIL means the dict is safe for reads; the threading.Lock in shared_state
    makes read-modify-write sequences atomic.

Twilio status callback payload (form-encoded POST):
    CallSid     — Twilio call identifier (matches call_sid on ScheduledCall)
    CallStatus  — "initiated" | "ringing" | "in-progress" | "completed"
                  | "failed" | "busy" | "no-answer" | "canceled"
    (other fields Twilio sends — we only use CallSid and CallStatus)
"""

import asyncio
import threading
import uvicorn
from fastapi import FastAPI, Form, Response

from shared_state import calls_lock, scheduled_calls

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

# docs_url / redoc_url disabled — no Swagger UI needed in production/hackathon
app = FastAPI(title="MyET Twilio Webhook", docs_url=None, redoc_url=None)

# Map Twilio terminal statuses → our ScheduledCall.status values.
# All non-"completed" terminal states are mapped to "failed" for simplicity.
# "initiated", "ringing", "in-progress" are not terminal — we ignore them.
_TERMINAL_STATUS_MAP = {
    "completed":  "completed",
    "failed":     "failed",
    "busy":       "failed",   # Called party was busy
    "no-answer":  "failed",   # Ring timeout with no pick-up
    "canceled":   "failed",   # Call was canceled before connecting
}


@app.post("/twilio/status")
async def twilio_status_callback(
    CallSid: str    = Form(...),
    CallStatus: str = Form(...),
):
    """
    Receive Twilio call status POSTs (application/x-www-form-urlencoded).

    Twilio sends this whenever call status changes. We only act on terminal
    statuses — completed, failed, busy, no-answer, canceled.

    Finds the ScheduledCall with the matching call_sid and updates its status
    when Twilio reports a terminal state.

    Returns 204 No Content — Twilio requires a 2xx response; 204 is the
    lightest response and avoids sending a body Twilio would ignore anyway.

    Example Twilio payload:
        CallSid=CAxxxx&CallStatus=completed&...
    """
    terminal_status = _TERMINAL_STATUS_MAP.get(CallStatus)
    if terminal_status:
        # We run the lock acquisition in a thread pool executor so we don't
        # block the uvicorn asyncio event loop thread while waiting for the lock.
        # threading.Lock is not awaitable — holding it directly in an async
        # function would stall the event loop if another thread holds the lock.
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _update_call_status, CallSid, terminal_status)

    # 204 is intentional: Twilio ignores the body, and sending empty 200 also works,
    # but 204 is the semantically correct "processed, no content to return" response.
    return Response(status_code=204)


def _update_call_status(call_sid: str, terminal_status: str) -> None:
    """
    Update ScheduledCall.status under the threading lock.

    Runs in a thread pool executor (called via run_in_executor from the async
    route) so the event loop is not blocked while acquiring calls_lock.
    """
    # Lock protects the read-scan-write sequence from concurrent updates.
    # Without the lock, two simultaneous webhook POSTs could both find the
    # same ScheduledCall and write conflicting statuses.
    with calls_lock:
        for call in scheduled_calls.values():
            if call.call_sid == call_sid:
                call.status = terminal_status
                print(f"[Webhook] {call_sid} → {terminal_status}")
                break  # call_sid is unique — no need to continue scanning


# ---------------------------------------------------------------------------
# Server bootstrap — called once from app.py on startup
# ---------------------------------------------------------------------------

# Module-level flag prevents double-starting on Streamlit reruns.
# Streamlit re-executes app.py on every user interaction; without this guard,
# uvicorn.run() would be called on every rerun, binding to port 8000 each time.
_server_started = False
_server_lock = threading.Lock()


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """
    Start the uvicorn server in a daemon thread (called once from app.py).

    The daemon thread dies automatically when the main Streamlit process exits,
    so no explicit cleanup is needed.

    Thread safety: _server_lock prevents two concurrent Streamlit reruns from
    both passing the _server_started check and starting two uvicorn instances.

    Args:
        host: Interface to bind to. "0.0.0.0" listens on all interfaces,
              which is required for ngrok / Twilio to reach the webhook.
        port: Port to listen on. Must match WEBHOOK_BASE_URL in config.py.
    """
    global _server_started
    with _server_lock:
        if _server_started:
            return  # Already running — skip on Streamlit reruns

        def _run() -> None:
            # log_level="warning" suppresses uvicorn's per-request access logs,
            # which would otherwise clutter the Streamlit terminal output.
            uvicorn.run(app, host=host, port=port, log_level="warning")

        # daemon=True: thread is killed automatically when the Streamlit process exits.
        # No explicit thread.join() or cleanup needed.
        thread = threading.Thread(target=_run, daemon=True, name="FastAPI-Webhook")
        thread.start()
        # Set flag AFTER thread.start() succeeds — if start() raises, the flag
        # stays False so the next call to start_server() can retry correctly.
        _server_started = True
    print(f"[Server] FastAPI webhook listening on {host}:{port}")
