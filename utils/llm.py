"""Gemini LLM wrapper."""
import re
import json
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

# Configure once on import
genai.configure(api_key=GEMINI_API_KEY)
_model = genai.GenerativeModel(GEMINI_MODEL)


def ask_llm(prompt: str, temperature: float = 0.7) -> str:
    """Send a prompt to Gemini and return the text response."""
    response = _model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
        ),
    )
    return response.text


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def ask_llm_json(prompt: str, temperature: float = 0.3) -> dict | list:
    """Send a prompt expecting JSON back. Returns parsed Python object."""
    full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
    response = _model.generate_content(
        full_prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=temperature,
        ),
    )
    raw = response.text.strip()
    raw = _strip_markdown_fences(raw)
    return json.loads(raw)
