"""
base_agent.py — Shared utilities for all agents.

Provides a simple helper to call OpenAI chat completions
with consistent error handling and logging.
"""
import logging
from typing import List, Dict
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)


async def chat_completion(
    messages: List[Dict],
    max_tokens: int = 300,
    temperature: float = 0.7,
) -> str:
    """
    Thin wrapper around OpenAI chat completions.
    Returns the assistant message content, or an empty string on failure.
    """
    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"OpenAI call failed: {e}", exc_info=True)
        return ""
