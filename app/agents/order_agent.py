"""
order_agent.py — Fully agentic AI agent using OpenAI function calling.

How it works:
  1. LLM receives customer message + conversation history + tool schemas
  2. LLM decides whether to call a tool or reply directly
  3. If tool call → execute tool → feed result back to LLM
  4. Repeat until LLM produces a final reply (finish_reason == "stop")
  5. Max 6 iterations to prevent runaway loops

This agent handles: price inquiries, orders, order status, complaints, escalation.
Fast intents (greeting, hours) are handled in the pipeline before reaching here.

Tools available (all free — no external APIs):
  search_products   → ChromaDB vector search
  create_order      → PostgreSQL
  lookup_order      → PostgreSQL
  escalate_to_human → PostgreSQL (sets ai_paused)
  get_business_info → PostgreSQL (business hours)
"""

import json
import logging
from typing import Dict, List, Optional, Union

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import Business, Customer
from app.services.rag import BusinessRAG
from app.agents.tools import TOOL_SCHEMAS, ToolExecutor

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)

MAX_ITERATIONS = 6  # max tool call rounds before forcing a plain reply


class OrderAgent:
    """
    Agentic AI that autonomously calls tools to handle complex customer requests.
    Returns either a plain string or an interactive dict (buttons/list) for WhatsApp.
    """

    def __init__(
        self,
        business: Business,
        customer: Customer,
        db: AsyncSession,
        language: str = "hinglish",
    ):
        self.business = business
        self.customer = customer
        self.db = db
        self.language = language
        self.rag = BusinessRAG(business.id)
        self.executor = ToolExecutor(
            db=db,
            business=business,
            customer=customer,
            rag=self.rag,
        )

    async def run(
        self,
        customer_message: str,
        history: List[Dict],
        intent: str,
    ) -> Union[str, dict]:
        """
        Run the agentic loop and return a reply for WhatsApp.
        """
        messages: List[dict] = [
            {"role": "system", "content": self._system_prompt(intent)},
            *history,
            {"role": "user", "content": customer_message},
        ]

        for iteration in range(MAX_ITERATIONS):
            try:
                response = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    max_tokens=512,
                    temperature=0.3,  # lower for reliable tool selection
                )
            except Exception as e:
                logger.error(
                    f"[OrderAgent] LLM call failed business={self.business.id} "
                    f"iter={iteration}: {e}",
                    exc_info=True,
                )
                return "Thoda technical issue aa gaya 🙏 Please thodi der mein dobara try karein."

            choice = response.choices[0]
            msg = choice.message

            # ── Final reply (no more tool calls) ──────────────────────────
            if choice.finish_reason == "stop" or not msg.tool_calls:
                raw = (msg.content or "").strip()
                if not raw:
                    return "Kuch samajh nahi aaya, please dobara batayein 🙏"
                logger.info(
                    f"[OrderAgent] business={self.business.id} intent={intent} "
                    f"done in {iteration + 1} iteration(s) reply_len={len(raw)}"
                )
                return self._parse_interactive(raw) or raw

            # ── Execute tool calls ────────────────────────────────────────
            # Append the assistant's tool-call message to history
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]})

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                tool_result = await self.executor.execute(fn_name, fn_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
                logger.debug(
                    f"[OrderAgent] tool={fn_name} result_len={len(tool_result)}"
                )

        # Exceeded max iterations — return safe fallback
        logger.warning(
            f"[OrderAgent] max iterations ({MAX_ITERATIONS}) reached "
            f"business={self.business.id} customer={self.customer.id}"
        )
        return "Main abhi check karke batata hoon 🙏 Thoda wait karein."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _system_prompt(self, intent: str) -> str:
        intent_context = {
            "purchase":      "Customer WANTS TO BUY. First search products, confirm with customer, then create_order after YES.",
            "price_inquiry": "Customer is asking about PRICES or PRODUCTS. Use search_products first, then suggest options.",
            "complaint":     "Customer has a COMPLAINT. Be empathetic first. Use escalate_to_human if unresolved.",
            "general":       "General query. Use search_products if product-related, get_business_info for hours/location.",
        }.get(intent, "General query. Use tools as needed.")

        return f"""You are an agentic WhatsApp sales assistant for a local Indian business.
Customer: {self.customer.name} | Phone: {self.customer.phone}
Business: {self.business.name} ({self.business.business_type or 'general'})

CURRENT INTENT: {intent_context}

━━━ YOUR JOB ━━━
You have tools. USE THEM to give accurate, real answers.
Never guess prices or product details — always call search_products first.
Never create an order without explicit customer confirmation.
Never make up order status — call lookup_order.

━━━ TOOL USAGE RULES ━━━
• search_products  → ALWAYS call first when customer asks about any product or price
• create_order     → ONLY after customer says "haan", "yes", "confirm", "order karo"
• lookup_order     → when customer asks "mera order", "status", "kahan hai"
• escalate_to_human→ for complaints, refund requests, or "insaan se baat karo"
• get_business_info→ for timings, location, contact questions

━━━ REPLY FORMAT ━━━
After tool results, reply to the customer in a friendly way.
Use WhatsApp formatting: *bold* for product names and prices.
Emojis: ✅ available  ❌ out of stock  🛍️ shopping  📦 order  🎁 offer

For choices with ≤3 options, return JSON (buttons):
{{"text": "Kaunsi size chahiye?", "buttons": [{{"id": "size_m", "title": "M / 32-34"}}, {{"id": "size_l", "title": "L / 36-38"}}]}}

For 4-10 options, return JSON (list):
{{"text": "Categories:", "sections": [{{"title": "Products", "rows": [{{"id": "cat_shirts", "title": "👕 Shirts", "description": "From ₹499"}}]}}]}}

━━━ LANGUAGE ━━━
Default Hinglish. Match customer's language. Sound like a friendly shopkeeper.
Use "Aap" for respect. Keep replies concise — max 5 lines."""

    @staticmethod
    def _parse_interactive(raw: str) -> Optional[dict]:
        """Try to parse LLM reply as interactive JSON (buttons/list)."""
        text = raw.strip()
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
