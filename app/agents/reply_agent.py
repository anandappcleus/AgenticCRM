import logging
from typing import List, Dict
from openai import AsyncOpenAI
from app.config import settings
from app.services.rag import BusinessRAG

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)


class ReplyAgent:
    """
    Core AI brain. Uses GPT-4o + RAG over business catalog to reply
    in Hinglish / Hindi / English based on what the customer sends.
    """

    def __init__(self, business_id: str):
        self.business_id = business_id
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

        # Build system prompt with RAG context
        system_prompt = self._build_system_prompt(context, customer_name)

        # Build message chain: system + conversation history + new message
        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": customer_message},
        ]

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        reply = response.choices[0].message.content.strip()
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

TONE EXAMPLES:
✅ Good: "Haan ji! Yeh wali jacket abhi available hai, ₹850 mein. Aapko kaisa size chahiye?"
❌ Bad: "Yes, the jacket is available at Rs. 850. Please let me know your size requirements."

BUSINESS KNOWLEDGE (use this to answer questions):
{rag_context}

IMPORTANT RULES:
1. Never make up prices or products not in the knowledge base
2. If you don't know something, say "Main abhi check karke batata hoon"
3. Never promise delivery dates you can't confirm
4. Keep replies SHORT — 2-4 sentences max (WhatsApp readers skim)
5. If customer seems ready to buy, ask for their address/size/preference to close the sale"""
