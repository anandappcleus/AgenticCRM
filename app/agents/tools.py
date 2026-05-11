"""
tools.py — OpenAI function-calling tool definitions + async implementations.

Each tool has:
  - A JSON schema (TOOL_SCHEMAS) the LLM uses to decide when/how to call it
  - An async implementation called by OrderAgent._execute_tool()

Tools (all free — use existing ChromaDB, PostgreSQL, Redis):
  search_products    → ChromaDB RAG vector search
  create_order       → PostgreSQL insert
  lookup_order       → PostgreSQL select
  escalate_to_human  → sets customer.ai_paused = True
  get_business_info  → returns business hours / contact from DB
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Business, Customer
from app.models import order as order_model
from app.models import customer as customer_model
from app.services.rag import BusinessRAG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool JSON schemas — passed to OpenAI as `tools=TOOL_SCHEMAS`
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search the business product catalog by natural language query. "
                "Use when the customer asks about products, prices, availability, or categories. "
                "Optionally filter by max_price or category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search, e.g. 'blue jacket under 1000'",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Optional maximum price filter in INR",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter, e.g. 'Shirts', 'Jackets'",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": (
                "Create a confirmed order after the customer explicitly confirms purchase. "
                "ONLY call this after the customer says YES or confirms. "
                "Never create an order speculatively."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of items to order",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_name": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 1},
                                "unit_price": {"type": "number", "minimum": 0},
                            },
                            "required": ["product_name", "quantity", "unit_price"],
                        },
                    },
                    "delivery_address": {
                        "type": "string",
                        "description": "Customer's delivery address (ask if not provided)",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any special instructions from the customer",
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "Look up the customer's most recent order and its current status. "
                "Use when customer asks 'mera order kahan hai' or 'order status'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Pause AI and hand over to human agent. "
                "Use for: unresolved complaints, refund requests, angry customers, "
                "or when customer explicitly asks to speak to a person."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Brief reason for escalation",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_business_info",
            "description": (
                "Get business operating hours and general info. "
                "Use when customer asks about timings, location, or contact."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor — called by OrderAgent
# ---------------------------------------------------------------------------

class ToolExecutor:
    """
    Executes tool calls requested by the LLM.
    Holds references to DB session, business, customer for tool implementations.
    """

    def __init__(
        self,
        db: AsyncSession,
        business: Business,
        customer: Customer,
        rag: BusinessRAG,
    ):
        self.db = db
        self.business = business
        self.customer = customer
        self.rag = rag

    async def execute(self, tool_name: str, arguments: dict) -> str:
        """Dispatch tool call and return a string result for the LLM."""
        logger.info(
            f"[Tool] business={self.business.id} customer={self.customer.id} "
            f"tool={tool_name} args={json.dumps(arguments)[:120]}"
        )
        try:
            if tool_name == "search_products":
                return await self._search_products(**arguments)
            elif tool_name == "create_order":
                return await self._create_order(**arguments)
            elif tool_name == "lookup_order":
                return await self._lookup_order()
            elif tool_name == "escalate_to_human":
                return await self._escalate_to_human(**arguments)
            elif tool_name == "get_business_info":
                return self._get_business_info()
            else:
                return f"[tool_error] Unknown tool: {tool_name}"
        except Exception as e:
            logger.error(f"[Tool] {tool_name} failed: {e}", exc_info=True)
            return f"[tool_error] {tool_name} failed: {str(e)}"

    # ------------------------------------------------------------------
    # Implementations
    # ------------------------------------------------------------------

    async def _search_products(
        self,
        query: str,
        max_price: Optional[float] = None,
        category: Optional[str] = None,
    ) -> str:
        """Vector search over ChromaDB catalog — free, no API cost."""
        enriched = query
        if max_price:
            enriched += f" price under {max_price}"
        if category:
            enriched += f" category {category}"

        results = await self.rag.query(enriched, top_k=5)

        if "No business knowledge" in results:
            return "No products found in catalog."

        # Post-filter by price if requested (RAG returns text; parse price lines)
        if max_price:
            filtered = []
            for block in results.split("\n---\n"):
                try:
                    price_line = [l for l in block.splitlines() if l.startswith("Price:")][0]
                    price_val = float(
                        price_line.replace("Price:", "").replace("₹", "").strip().split()[0].replace(",", "")
                    )
                    if price_val <= max_price:
                        filtered.append(block)
                except (IndexError, ValueError):
                    filtered.append(block)
            results = "\n---\n".join(filtered) if filtered else "No products found within that price range."

        return results

    async def _create_order(
        self,
        items: list,
        delivery_address: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Create order in PostgreSQL and return confirmation string."""
        order = await order_model.create_order(
            db=self.db,
            customer_id=self.customer.id,
            business_id=self.business.id,
            items=items,
            delivery_address=delivery_address,
            notes=notes,
        )
        item_lines = "\n".join(
            f"  • {i['product_name']} x{i['quantity']} @ ₹{i['unit_price']}"
            for i in items
        )
        return (
            f"Order created successfully!\n"
            f"Order ID: {order.id[:8].upper()}\n"
            f"Items:\n{item_lines}\n"
            f"Total: ₹{order.total_amount:.0f}\n"
            f"Status: {order.status}\n"
            f"Address: {delivery_address or 'Not provided'}"
        )

    async def _lookup_order(self) -> str:
        """Fetch latest order from PostgreSQL."""
        order = await order_model.get_latest_order(self.db, self.customer.id)
        if not order:
            return "No orders found for this customer."
        return (
            f"Latest order:\n"
            f"Order ID: {order.id[:8].upper()}\n"
            f"Status: {order.status}\n"
            f"Total: ₹{order.total_amount:.0f}\n"
            f"Placed: {order.created_at.strftime('%d %b %Y') if order.created_at else 'N/A'}\n"
            f"Address: {order.delivery_address or 'Not provided'}"
        )

    async def _escalate_to_human(self, reason: str) -> str:
        """Pause AI for this customer so the owner can take over."""
        await customer_model.set_ai_paused(self.db, self.customer.id, True)
        logger.warning(
            f"[Tool] Escalated to human: customer={self.customer.id} reason={reason}"
        )
        return f"Escalated. AI paused for customer. Reason: {reason}"

    def _get_business_info(self) -> str:
        """Return business hours and info from DB (no API call needed)."""
        hours = self.business.business_hours or "Not specified"
        name = self.business.name
        btype = self.business.business_type or "general"
        return (
            f"Business: {name}\n"
            f"Type: {btype}\n"
            f"Operating hours: {hours}"
        )
