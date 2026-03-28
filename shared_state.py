"""
shared_state.py — Thread-safe in-memory store for ScheduledCall objects.

Imported by: app.py, server.py, and APScheduler job closures.
All three run in the same Python process and share these objects directly.

Why a separate module:
    Python's module system executes a module exactly once per interpreter.
    Subsequent imports return the cached module object — so `scheduled_calls`
    is the same dict instance everywhere that imports it.
"""

import threading
from models.schemas import ScheduledCall

# ---------------------------------------------------------------------------
# Shared call registry
# ---------------------------------------------------------------------------

# All active/historical calls for this session, keyed by ScheduledCall.id.
# Example entry:
#   "3f7c9e..." → ScheduledCall(id="3f7c9e...", phone_number="+91...", status="calling")
scheduled_calls: dict[str, ScheduledCall] = {}

# ---------------------------------------------------------------------------
# Synchronisation primitive
# ---------------------------------------------------------------------------

# Protects atomic read-modify-write sequences across threads.
# Pattern:
#   with calls_lock:
#       existing = scheduled_calls.get(call_id)
#       if existing:
#           existing.status = "completed"
calls_lock = threading.Lock()
