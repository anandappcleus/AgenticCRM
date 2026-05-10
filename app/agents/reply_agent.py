import logging
from typing import List, Dict, Optional
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
    ) -> str:
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
            reply = response.choices[0].message.content.strip()
            if not reply:
                raise ValueError("NIM returned empty reply")
        except Exception as e:
            logger.error(
                f"[ReplyAgent] NIM call failed for business={self.business_id} intent={intent}: {e}",
                exc_info=True,
            )
            return "Abhi ek technical problem aa rahi hai, thoda wait karein. Hum jaldi reply karenge! 🙏"

        logger.info(f"[ReplyAgent] business={self.business_id} intent={intent} reply_len={len(reply)}")
        return reply

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
- End responses with a helpful question or call to action

WHATSAPP FORMATTING (always use these — they render natively in WhatsApp):
- Wrap product names in *asterisks* for bold: *Silk Saree*
- Wrap prices in *asterisks* for bold: *₹1,200*
- Use emojis naturally: ✅ for available, ❌ for out of stock, 🛍️ for products, 📦 for orders, 🎁 for offers, 💬 for questions
- Use bullet points with • for listing multiple products or features
- Use numbered lists (1. 2. 3.) for steps like ordering or payment
- Separate sections with a blank line for readability
- Keep replies SHORT — 3-5 lines max for general chat, up to 8 lines for product listings

FORMATTING EXAMPLES BY INTENT:

Product inquiry → list clearly:
*Banarasi Silk Saree* 🛍️
• Price: *₹2,500*
• Colors: Red, Blue, Green
• Available: ✅
Aapko kaunsa color pasand hai?

General greeting → warm and brief:
Namaste {customer_name} ji! 😊 Kaise help kar sakta hoon aapki aaj?

Order confirmation → structured:
✅ *Order Confirm!*
1. Product: Silk Saree (Red)
2. Size: Free size
3. Delivery: 3-5 din
Payment ke liye UPI send karein: *shop@upi* 🙏

BUSINESS KNOWLEDGE (use this to answer questions):
{rag_context}

IMPORTANT RULES:
1. Never make up prices or products not in the knowledge base
2. If you don't know something, say "Main abhi check karke batata hoon 🙏"
3. Never promise delivery dates you can't confirm
4. Always use WhatsApp formatting — no plain text walls
5. If customer seems ready to buy, ask for their address/size/preference to close the sale"""
