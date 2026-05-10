"""
intent.py — Fast, zero-cost intent classifier using keyword matching.

Run this BEFORE the GPT call to avoid unnecessary API costs.
Handles Hinglish, Hindi, and English keywords.

Intents:
  purchase       → customer wants to buy
  price_inquiry  → asking about price / offer / discount
  complaint      → problem, refund, return
  hours          → shop timings
  greeting       → hi / namaste / hello
  general        → fallback (catch-all)
"""

from typing import Dict, List

INTENT_KEYWORDS: Dict[str, List[str]] = {
    # Check complaint first — "refund chahiye" must not match purchase
    "complaint": [
        "problem", "issue", "wrong", "refund", "return",
        "damage", "bura", "complaint", "worst", "horrible",
        "kharab", "wapas", "bhejiye", "nahi chala", "tuta",
    ],
    "purchase": [
        "order", "buy", "khareedna", "chahiye", "lena hai",
        "book", "confirm", "place order", "ready", "deliver",
        "bhej do", "send karo", "le lena", "purchase",
    ],
    "price_inquiry": [
        "price", "kitna", "rate", "cost", "daam", "dam",
        "rupee", "₹", "rs", "discount", "offer", "cheap",
        "sasta", "costly", "mahenga", "kitne ka", "kya rate",
    ],
    "hours": [
        "open", "close", "time", "timing", "kab",
        "khula", "band", "sunday", "holiday", "aaj",
        "kal", "weekend", "saturday",
    ],
    "greeting": [
        "hello", "hi", "namaste", "haan", "hey",
        "good morning", "good evening", "bhai", "bhaiya",
        "didi", "sir", "madam", "ji",
    ],
}


def classify_intent(text: str) -> str:
    """Return the most likely intent label for a given message."""
    text_lower = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return "general"
