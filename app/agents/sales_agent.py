import logging
from typing import Optional
from openai import AsyncOpenAI
from app.config import settings
from app.services.rag import BusinessRAG

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class SalesAgent:
    """
    Proactively suggests products and appends offers when a customer
    shows purchase or price-inquiry intent.
    """

    def __init__(self, business_id: str):
        self.business_id = business_id
        self.rag = BusinessRAG(business_id)

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
            "Write ONE short upsell or cross-sell suggestion in Hinglish. "
            "Max 1 sentence. Don't repeat what was already said. "
            "Example: \"Saath mein yeh matching belt bhi dekh sakte hain — sirf ₹250 mein!\""
        )

        try:
            resp = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                temperature=0.6,
            )
            suggestion = resp.choices[0].message.content.strip()
            return suggestion if suggestion else None
        except Exception as e:
            logger.warning(f"SalesAgent failed: {e}")
            return None
