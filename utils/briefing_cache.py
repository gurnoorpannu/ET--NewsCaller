"""
utils/briefing_cache.py — Disk-based briefing cache.

=== How it works ===

    Saves the pipeline output (Briefing) to a JSON file on disk.
    On the next run, if a cached briefing exists for the SAME user profile
    AND it was generated today, we load it instead of re-running the pipeline.

    Cache file location:  .briefing_cache/<cache_key>.json
    Cache key:            MD5 of (name + role + sorted interests + depth + today's date)
    TTL:                  One calendar day (cache is invalidated at midnight)

=== Why disk (not session_state) ===

    Streamlit session_state resets when you refresh or restart the server.
    A disk cache survives server restarts, making it useful during development
    when you're repeatedly tweaking app.py and re-running `streamlit run app.py`.

=== Usage ===

    from utils.briefing_cache import load_cached_briefing, save_briefing_to_cache

    cached = load_cached_briefing(profile)
    if cached:
        briefing = cached          # skip pipeline entirely
    else:
        briefing = run_pipeline(profile)
        save_briefing_to_cache(profile, briefing)
"""

import hashlib
import json
import os
from datetime import date
from pathlib import Path

from models.schemas import Briefing, UserProfile

# ── Cache directory (sits next to this file's parent) ──────────────────────────
# Stored at project root in .briefing_cache/ (gitignored)
_CACHE_DIR = Path(__file__).parent.parent / ".briefing_cache"


def _cache_key(profile: UserProfile) -> str:
    """
    Build a unique cache key from the user profile + today's date.

    Two runs with identical profiles on the SAME day hit the same cache entry.
    A new day means a new key → fresh briefing automatically.

    Components hashed:
        - profile.name       (who the user is)
        - profile.role       (their job/role)
        - profile.interests  (sorted for stability regardless of input order)
        - profile.preferred_depth
        - today's date       (YYYY-MM-DD)
    """
    raw = "|".join([
        profile.name.strip().lower(),
        profile.role.strip().lower(),
        ",".join(sorted(i.strip().lower() for i in profile.interests)),
        profile.preferred_depth,
        str(date.today()),          # cache expires at midnight
    ])
    return hashlib.md5(raw.encode()).hexdigest()


def load_cached_briefing(profile: UserProfile) -> Briefing | None:
    """
    Load a cached Briefing for this profile, or return None if not found / stale.

    Returns:
        Briefing object if a valid same-day cache hit exists, else None.
    """
    _CACHE_DIR.mkdir(exist_ok=True)
    cache_file = _CACHE_DIR / f"{_cache_key(profile)}.json"

    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        briefing = Briefing.model_validate(data)
        print(f"[cache] HIT — loaded briefing from {cache_file.name}")
        return briefing
    except Exception as e:
        # Corrupted cache file — treat as miss
        print(f"[cache] MISS (corrupt file: {e})")
        cache_file.unlink(missing_ok=True)
        return None


def save_briefing_to_cache(profile: UserProfile, briefing: Briefing) -> None:
    """
    Persist a Briefing to disk under the profile's cache key.

    Silently swallows errors — caching is best-effort and should never
    block the main pipeline from completing.
    """
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        cache_file = _CACHE_DIR / f"{_cache_key(profile)}.json"
        cache_file.write_text(
            briefing.model_dump_json(indent=2),
            encoding="utf-8",
        )
        print(f"[cache] SAVED — {cache_file.name}")
    except Exception as e:
        print(f"[cache] WARNING: could not save briefing to cache: {e}")
