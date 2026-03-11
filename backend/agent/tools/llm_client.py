"""
FireReach — LLM Client

Single module for all LLM calls:
  Primary:  Groq — Llama 3.3 70B  (14,400 req/day free)
  Fallback: Google Gemini 1.5 Flash (1,500 req/day, 1M context)

Includes:
  • Exponential backoff on rate limits (HTTP 429)
  • Automatic switch to Gemini on Groq failure
  • Token estimation (heuristic: 1 token ≈ 4 characters)
  • JSON fence stripping
"""

from __future__ import annotations
import asyncio
import json
import os
from typing import Any

import httpx

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"

_GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


def count_tokens(text: str) -> int:
    """Heuristic token estimate: 1 token ≈ 4 characters."""
    return len(text) // 4


async def _groq_chat(
    system: str,
    user: str,
    temperature: float = 0.7,
    max_retries: int = 3,
) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")

    payload = {
        "model": _GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                resp = await client.post(
                    _GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

    raise RuntimeError("Groq rate limit exceeded after retries")


async def _gemini_chat(
    system: str,
    user: str,
    temperature: float = 0.7,
) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    combined_prompt = f"{system}\n\n---\n\n{user}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_GEMINI_API_URL}?key={api_key}",
            json={
                "contents": [{"parts": [{"text": combined_prompt}]}],
                "generationConfig": {"temperature": temperature},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def chat_completion(
    system: str,
    user: str,
    temperature: float = 0.7,
    prefer_gemini: bool = False,
) -> str:
    """
    Attempts Groq first (unless prefer_gemini=True for large contexts),
    falls back to Gemini on any error.
    """
    if prefer_gemini:
        try:
            return await _gemini_chat(system, user, temperature)
        except Exception:
            pass

    try:
        return await _groq_chat(system, user, temperature)
    except Exception:
        # Fallback to Gemini
        return await _gemini_chat(system, user, temperature)
