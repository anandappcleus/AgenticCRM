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
        "payment", "pay", "dena hai", "bhugtan", "paisa",
        "upi", "gpay", "paytm", "razorpay", "neft", "cash",
        "online pay", "card", "nhi dena", "nahi dena",
    ],
    "hours": [
        "open", "close", "time", "timing", "kab",
        "khula", "band", "sunday", "holiday", "aaj",
        "kal", "weekend", "saturday",
    ],
    "greeting": [
        "hello", "hi", "namaste", "haan", "hey",
        "good morning", "good evening", "bhai", "bhaiya",
        "didi", "sir", "madam",
    ],
}


def classify_intent(text: str) -> str:
    """Return the most likely intent label for a given message."""
    text_lower = text.lower()

    # Button tap IDs / titles map directly to intent
    _BUTTON_INTENT_MAP = {
        "see_products":   "price_inquiry",
        "check_offers":   "price_inquiry",
        "contact_owner":  "general",
        "order_now":      "purchase",
        "see_more":       "price_inquiry",
        "ask_question":   "general",
        "confirm_order":  "purchase",
        "change_item":    "purchase",
        "cancel_order":   "complaint",
        "request_refund": "complaint",
        "call_owner":     "complaint",
        "send_photo":     "complaint",
        # Payment button IDs
        "pay_cash":       "purchase",
        "pay_card":       "purchase",
        "pay_online":     "purchase",
        "pay_paytm":      "purchase",
        "pay_gpay":       "purchase",
        "pay_razor":      "purchase",
        # Button titles (what the model sees)
        "🛍️ products":   "price_inquiry",
        "🎁 offers":      "price_inquiry",
        "🛒 order now":   "purchase",
        "✅ confirm order": "purchase",
        "🔄 request refund": "complaint",
    }
    for key, intent in _BUTTON_INTENT_MAP.items():
        if key in text_lower:
            return intent

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return intent
    return "general"
