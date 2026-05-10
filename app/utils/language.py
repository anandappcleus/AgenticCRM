"""
language.py — Helpers for Hindi / Hinglish text processing.
"""
import re


HINDI_UNICODE_RANGE = re.compile(r"[\u0900-\u097F]")
ENGLISH_ONLY = re.compile(r"^[a-zA-Z0-9\s\.,!?'\"@#\-₹%&()\[\]{}:;/\\]+$")


def detect_script(text: str) -> str:
    """
    Detect whether the message is primarily Hindi (Devanagari),
    English, or Hinglish (mixed).
    """
    hindi_chars = len(HINDI_UNICODE_RANGE.findall(text))
    total_chars = len(text.replace(" ", ""))
    if total_chars == 0:
        return "hinglish"
    ratio = hindi_chars / total_chars
    if ratio > 0.5:
        return "hindi"
    if ENGLISH_ONLY.match(text):
        return "english"
    return "hinglish"


def normalize_hinglish(text: str) -> str:
    """Basic normalization: strip extra whitespace, lowercase."""
    return " ".join(text.strip().split()).lower()


def truncate_for_whatsapp(text: str, max_chars: int = 4096) -> str:
    """WhatsApp text messages have a 4096-char limit."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
