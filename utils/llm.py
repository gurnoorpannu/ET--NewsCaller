"""Gemini LLM wrapper — uses REST API directly (compatible with Python 3.14+)."""
import re
import json
import time
import requests
from config import GEMINI_API_KEY, GEMINI_MODEL

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _call_gemini(prompt: str, temperature: float = 0.7) -> str:
    """
    Call Gemini REST API with retry on 429 rate-limit errors.

    Key sent via 'x-goog-api-key' header (not URL param) to keep it
    out of server logs and Python tracebacks.

    Retries up to 4 times with exponential back-off on 429.
    Raises RuntimeError after all attempts are exhausted.
    """
    # API key in header — never in the URL where it leaks into logs
    url = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent"
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    last_response = None
    for attempt in range(4):  # attempts 0-3 (4 total)
        resp = requests.post(url, json=payload, headers=headers, timeout=30)

        if resp.status_code == 429:
            # Back-off: 10s, 20s, 30s, 40s
            wait = 10 * (attempt + 1)
            print(f"[LLM] Rate limited. Waiting {wait}s (attempt {attempt + 1}/4)...")
            time.sleep(wait)
            last_response = resp
            continue  # retry

        # For any non-429 error, raise immediately (400, 500, etc.)
        resp.raise_for_status()

        # Success — parse and return
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    # All 4 attempts were rate-limited
    raise RuntimeError(
        f"Gemini API rate limit exhausted after 4 attempts. "
        f"Last HTTP status: {last_response.status_code if last_response else 'unknown'}"
    )


def ask_llm(prompt: str, temperature: float = 0.7) -> str:
    """Send a prompt to Gemini and return the text response."""
    return _call_gemini(prompt, temperature)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def ask_llm_json(prompt: str, temperature: float = 0.3) -> dict | list:
    """
    Send a prompt expecting JSON back. Returns parsed Python dict or list.

    Raises ValueError if Gemini returns valid JSON that isn't a dict or list
    (e.g. a bare string or number), since all callers expect a structured object.
    """
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
    raw = _call_gemini(full_prompt, temperature).strip()
    raw = _strip_markdown_fences(raw)
    result = json.loads(raw)

    # Guard: all callers expect a dict or list, not a scalar
    if not isinstance(result, (dict, list)):
        raise ValueError(
            f"Gemini returned valid JSON but not a dict/list: {type(result).__name__!r} — raw: {raw[:100]}"
        )
    return result
