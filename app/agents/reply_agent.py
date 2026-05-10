import json
import logging
from typing import Dict, List, Optional, Union
from openai import AsyncOpenAI
from app.config import settings
from app.services.rag import BusinessRAG

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)


class ReplyAgent:
    """
    Core AI brain. Uses NIM + RAG over business catalog to reply
    in Hinglish / Hindi / English based on what the customer sends.
    Supports per-tenant system_prompt, business_type, and language.
    """

    def __init__(
        self,
        business_id: str,
        system_prompt: Optional[str] = None,
        business_type: Optional[str] = None,
        language: str = "hinglish",
    ):
        self.business_id = business_id
        self.custom_system_prompt = system_prompt  # per-tenant override
        self.business_type = business_type or "general"
        self.language = language
        self.rag = BusinessRAG(business_id)

    async def run(
        self,
        customer_message: str,
        history: List[Dict],
        customer_name: str,
        intent: str,
    ) -> Union[str, dict]:
        """
        Returns either:
          - str  → plain WhatsApp text
          - dict → {"text": str, "buttons": [...]}  for interactive buttons
                   {"text": str, "sections": [...]}  for list message
        """
        # Fetch relevant business knowledge via RAG
        context = await self.rag.query(customer_message, top_k=4)
        if "No business knowledge" in context:
            logger.warning(f"[ReplyAgent] business={self.business_id} RAG empty — using generic reply")

        # Build system prompt: use per-tenant custom prompt or default
        if self.custom_system_prompt:
            system_prompt = self.custom_system_prompt.replace("{rag_context}", context).replace("{customer_name}", customer_name)
            logger.info(f"[ReplyAgent] business={self.business_id} using custom system prompt")
        else:
            system_prompt = self._build_system_prompt(context, customer_name)

        # Build message chain: system + conversation history + new message
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": customer_message},
        ]

        try:
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=messages,
                max_tokens=400,
                temperature=0.7,
            )
            raw = response.choices[0].message.content.strip()
            if not raw:
                raise ValueError("NIM returned empty reply")
        except Exception as e:
            logger.error(
                f"[ReplyAgent] NIM call failed for business={self.business_id} intent={intent}: {e}",
                exc_info=True,
            )
            return "Abhi ek technical problem aa rahi hai, thoda wait karein. Hum jaldi reply karenge! 🙏"

        # Try parsing as interactive JSON (LLM decided to use buttons/list)
        parsed = self._try_parse_interactive(raw)
        if parsed:
            kind = "buttons" if "buttons" in parsed else "list"
            logger.info(
                f"[ReplyAgent] business={self.business_id} intent={intent} "
                f"interactive={kind} text_len={len(parsed.get('text', ''))}"
            )
            return parsed

        logger.info(f"[ReplyAgent] business={self.business_id} intent={intent} reply_len={len(raw)}")
        return raw

    @staticmethod
    def _try_parse_interactive(raw: str) -> Optional[dict]:
        """Extract JSON from LLM response. Returns dict if valid interactive payload, else None."""
        text = raw.strip()
        # Strip markdown code fences if present (```json ... ```)
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "text" in data:
                if "buttons" in data or "sections" in data:
                    return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    def _build_system_prompt(self, rag_context: str, customer_name: str) -> str:
        return f"""You are a helpful WhatsApp assistant for a local Indian business.
Customer name: {customer_name}

ROLE:
- You reply on behalf of the business owner
- You are friendly, warm, and professional
- Speak in Hinglish (mix of Hindi and English) by default

LANGUAGE RULES:
- Default: Hinglish (e.g., "Aapka jacket ₹850 mein milega!")
- If customer writes in pure Hindi → reply in Hindi
- If customer writes in English → reply in English
- Never use formal/robotic language. Sound like a real shopkeeper.
- Use "Aap" for respect, not "Tum"

PLAIN TEXT FORMATTING (when not using buttons):
- Wrap product names in *asterisks* for bold: *Silk Saree*
- Wrap prices in *asterisks* for bold: *₹1,200*
- Use emojis naturally: ✅ available, ❌ out of stock, 🛍️ products, 📦 orders, 🎁 offers
- Use • bullet points for listing multiple items
- Keep replies SHORT — 3-5 lines max

INTERACTIVE BUTTONS (JSON format — use when asking a question with ≤3 fixed choices):
Return ONLY the JSON object, nothing else before or after it:

{{"text": "Kaunsi size chahiye aapko?", "buttons": [{{"id": "size_s", "title": "S (28-30)"}}, {{"id": "size_m", "title": "M (32-34)"}}, {{"id": "size_l", "title": "L (36-38)"}}]}}

INTERACTIVE LIST (JSON — use for 4-10 options like categories or appointment slots):

{{"text": "Kaunsi category dekhna chahte hain?", "sections": [{{"title": "Products", "rows": [{{"id": "cat_shirts", "title": "Shirts", "description": "From ₹499"}}, {{"id": "cat_pants", "title": "Pants", "description": "From ₹699"}}, {{"id": "cat_jackets", "title": "Jackets", "description": "From ₹999"}}]}}]}}

USE BUTTONS FOR: size selection, color choice, yes/no confirm, payment method (≤3 options)
USE LIST FOR: product categories, FAQ topics, appointment slots (4+ options)
USE PLAIN TEXT FOR: greetings, product info, order confirmations, open-ended questions

BUTTON RULES:
- Button id: short, lowercase, underscored — size_m, confirm_yes, color_red
- Button title: max 20 characters
- Never nest buttons inside plain text — return ONLY the JSON when using buttons

BUSINESS KNOWLEDGE (use this to answer questions):
{rag_context}

IMPORTANT RULES:
1. Never make up prices or products not in the knowledge base
2. If you don't know something, say "Main abhi check karke batata hoon 🙏"
3. Never promise delivery dates you can't confirm
4. When customer is ready to buy, use yes/no confirm buttons to close the sale
5. After customer taps a button (message starts with S, M, L, Yes, No etc.) — continue the conversation naturally"""
