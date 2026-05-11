import logging
from typing import Optional
from openai import AsyncOpenAI
from app.config import settings
from app.services.rag import BusinessRAG, get_rag

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)


class SalesAgent:
    """
    Proactively suggests products and appends offers when a customer
    shows purchase or price-inquiry intent.
    """

    def __init__(self, business_id: str):
        self.business_id = business_id
        self.rag = get_rag(business_id)

    async def get_offer(self, customer_message: str) -> Optional[str]:
        """
        Return a short offer/suggestion string to append to the reply,
        or None if nothing relevant.
        """
        # Fetch top matching products
        context = await self.rag.query(customer_message, top_k=2)

        if not context or "No business knowledge" in context:
            return None

        prompt = (
            f"Customer is asking: \"{customer_message}\"\n\n"
            f"Relevant products:\n{context}\n\n"
            "Write ONE short upsell or cross-sell suggestion in Hinglish using WhatsApp formatting. "
            "Use *bold* for product name and price. Add 1 relevant emoji. Max 2 lines. "
            "Don't repeat what was already said in the main reply. "
            "Example: \"🎁 Saath mein *Matching Belt* bhi available hai — sirf *₹250* mein! Lena hai?\""
        )

        try:
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.6,
            )
            suggestion = resp.choices[0].message.content.strip()
            if suggestion:
                logger.info(f"[SalesAgent] business={self.business_id} offer appended: {suggestion[:60]}")
                return suggestion
            logger.warning(f"[SalesAgent] business={self.business_id} NIM returned empty offer")
            return None
        except Exception as e:
            logger.error(f"[SalesAgent] business={self.business_id} NIM call failed: {e}", exc_info=True)
            return None
