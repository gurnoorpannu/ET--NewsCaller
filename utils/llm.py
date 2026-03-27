"""Gemini LLM wrapper — uses REST API directly (compatible with Python 3.14+)."""
import re
import json
import time
import requests
from config import GEMINI_API_KEY, GEMINI_MODEL

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _call_gemini(prompt: str, temperature: float = 0.7) -> str:
    """Call Gemini REST API with retry on 429 rate limit errors."""
    url = f"{_BASE_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    for attempt in range(4):  # up to 4 attempts
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 429:
            wait = 10 * (attempt + 1)  # 10s, 20s, 30s, 40s
            print(f"[LLM] Rate limited. Waiting {wait}s before retry {attempt + 1}/3...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    # Final attempt after waits
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


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
    """Send a prompt expecting JSON back. Returns parsed Python object."""
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
    raw = _call_gemini(full_prompt, temperature).strip()
    raw = _strip_markdown_fences(raw)
    return json.loads(raw)
