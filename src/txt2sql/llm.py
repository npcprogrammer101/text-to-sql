"""
Local LLM layer — talks to Ollama over HTTP. This is the pluggable seam: swap
the `Ollama` class for any other client with a `.complete()` method and the
agents don't change.

Also home to `parse_list_output`, the safe replacement for the original
project's `eval()` on model output. Models are asked to return JSON-ish lists;
we parse them with ast.literal_eval / json, never by executing the string.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any

import requests

from .config import settings


class Ollama:
    """Minimal Ollama chat client. No external SDK needed."""

    def __init__(self, model: str, host: str | None = None, temperature: float = 0.0):
        self.model = model
        self.host = (host or settings.ollama_host).rstrip("/")
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        resp = requests.post(
            f"{self.host}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": self.temperature},
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# SAFE structured-output parsing (replaces eval())
# ---------------------------------------------------------------------------
def parse_list_output(text: str) -> Any:
    """
    Extract a Python list from model output WITHOUT executing it.

    The original project did `eval(model_output)` — running the model's text as
    code. Here we strip fences, isolate the outermost [...] block, and parse it
    with ast.literal_eval (falling back to json). literal_eval only accepts
    literals — lists, dicts, strings, numbers — so there is no code-execution
    path even on adversarial output.
    """
    cleaned = text.replace("```json", "").replace("```", "").strip()

    # isolate the outermost bracketed region if there's surrounding prose
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    # try literal_eval first (handles single quotes), then json
    for parser in (ast.literal_eval, json.loads):
        try:
            result = parser(cleaned)
            if isinstance(result, (list, dict)):
                return result
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue

    raise ValueError(f"Could not parse a list from model output:\n{text[:300]}")
