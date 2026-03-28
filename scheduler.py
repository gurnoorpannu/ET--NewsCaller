"""
scheduler.py — APScheduler singleton for firing scheduled call jobs.

APScheduler's BackgroundScheduler runs jobs in a thread pool inside the same
Python process. This module initialises and starts it exactly once, regardless
of how many times Streamlit reruns the module.

Usage from app.py:
    from scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.add_job(fn, 'date', run_date=utc_datetime, id=call_id)
"""

import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------

# Module-level singleton — initialised on first call to get_scheduler().
# Type annotation uses the newer union syntax (Python 3.10+), matching the
# style already used in shared_state.py (dict[str, ScheduledCall]).
_scheduler: BackgroundScheduler | None = None
_scheduler_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_scheduler() -> BackgroundScheduler:
    """
    Return the singleton BackgroundScheduler, starting it if not yet running.

    Thread-safe: uses _scheduler_lock to prevent a race condition where two
    concurrent Streamlit reruns both see _scheduler == None and start two
    schedulers. Safe to call from any thread.

    Configuration:
        ThreadPoolExecutor(max_workers=4):
            Allows up to 4 jobs to run in parallel. Unlikely to be needed
            for a hackathon demo, but a safe default that won't starve the
            event loop if multiple scheduled calls fire at the same second.

        misfire_grace_time=60:
            If Streamlit is briefly frozen during a rerun and a job fires up
            to 60 seconds late, APScheduler still runs it rather than
            silently dropping it. Prevents missed calls on slow machines.

    Returns:
        The running BackgroundScheduler singleton.

    Example usage:
        scheduler = get_scheduler()
        scheduler.add_job(
            my_call_fn,         # callable to execute
            trigger='date',     # fire once at a specific datetime
            run_date=utc_dt,    # UTC datetime when to fire
            id=call_id,         # used to cancel with scheduler.remove_job(id)
        )
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            # ThreadPoolExecutor allows APScheduler to run multiple jobs concurrently.
            # 'default' is the executor name APScheduler uses internally.
            _scheduler = BackgroundScheduler(
                executors={"default": ThreadPoolExecutor(max_workers=4)},
                job_defaults={"misfire_grace_time": 60},
            )
            _scheduler.start()
            print("[Scheduler] APScheduler BackgroundScheduler started.")
    return _scheduler
