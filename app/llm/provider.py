"""LLM provider abstraction with fallbacks and graceful degradation.

All LLM calls must go through this module. On failure of all providers it
raises LLMUnavailable so callers can degrade (hard rule 6). No provider SDK
calls anywhere else.
"""

from __future__ import annotations

import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class LLMUnavailable(Exception):
    pass


class Provider:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        llm_cfg = self.config.get("llm", {})
        self.providers = llm_cfg.get("providers", ["gemini", "groq", "openrouter"])
        self.timeout = llm_cfg.get("timeout_seconds", 20)
        self.max_retries = llm_cfg.get("max_retries", 2)

    def _complete_gemini(self, prompt: str, **kwargs) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        import httpx

        model = kwargs.get("model") or os.getenv("GEMINI_MODEL") or "gemini-flash-latest"
        temperature = kwargs.get("temperature", 0)
        max_tokens = kwargs.get("max_tokens", 256)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "text/plain",
            },
        }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, json=body)
            r.raise_for_status()
            j = r.json()
        # extract text
        try:
            return j["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            return ""

    def _complete_groq(self, prompt: str, **kwargs) -> str:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        import httpx

        model = kwargs.get("model") or os.getenv("GROQ_MODEL") or "qwen/qwen3.8-27b"
        temperature = kwargs.get("temperature", 0)
        max_tokens = kwargs.get("max_tokens", 256)
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            j = r.json()
        try:
            return j["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""

    def _complete_openrouter(self, prompt: str, **kwargs) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        import httpx

        model = kwargs.get("model") or os.getenv("OPENROUTER_MODEL") or "google/gemini-2.5-flash-lite"
        temperature = kwargs.get("temperature", 0)
        max_tokens = kwargs.get("max_tokens", 256)
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "http://localhost:8000"),
            "X-Title": os.getenv("OPENROUTER_TITLE", "Mutabiq"),
        }
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(url, headers=headers, json=body)
            r.raise_for_status()
            j = r.json()
        try:
            return j["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""

    def complete(self, prompt: str, **kwargs) -> str:
        last_err: Exception | None = None
        for pname in self.providers:
            for attempt in range(self.max_retries + 1):
                try:
                    if pname == "gemini":
                        return self._complete_gemini(prompt, **kwargs)
                    if pname == "groq":
                        return self._complete_groq(prompt, **kwargs)
                    if pname == "openrouter":
                        return self._complete_openrouter(prompt, **kwargs)
                except Exception as e:
                    last_err = e
                    time.sleep(0.1 * (attempt + 1))
        raise LLMUnavailable(f"All LLM providers failed: {last_err}") from last_err
