import asyncio
import logging
import time
from app.services.whatsapp import (
    IncomingMessage, send_whatsapp_message,
    send_whatsapp_buttons, send_whatsapp_list,
    mark_as_read,
)
from app.agents.reply_agent import ReplyAgent
from app.agents.sales_agent import SalesAgent
from app.services.scheduler import schedule_followup, cancel_followup
from app.models.database import AsyncSessionLocal
from app.models import customer as customer_model
from app.models import conversation as conv_model
from app.models import lead as lead_model
from app.models.business import get_business_by_phone_id
from app.utils.intent import classify_intent

logger = logging.getLogger(__name__)


async def process_message(msg: IncomingMessage) -> None:
    """
    Main AI pipeline. Runs as a FastAPI BackgroundTask.
    Flow:
      1.  Resolve business from phone_id
      2.  Upsert customer
      3.  Save incoming message + mark as read  (parallel)
      4.  Cancel pending follow-up
      5.  Classify intent (keyword, zero-cost)
      6.  Build conversation history
      7.  Reply Agent + Sales Agent             (parallel when intent warrants it)
      8.  Combine reply + offer, send via WhatsApp
      9.  Save AI response + upsert lead        (parallel)
      10. Schedule follow-up
    """
    t0 = time.monotonic()
    async with AsyncSessionLocal() as db:
        try:
            # 1. Resolve business
            business = await get_business_by_phone_id(db, msg.whatsapp_phone_id)
            if business is None:
                logger.warning(
                    f"No business found for phone_id={msg.whatsapp_phone_id}. "
                    "Register via POST /api/v1/business/register"
                )
                return

            if not business.ai_active:
                logger.info(f"AI disabled for business={business.id}. Skipping.")
                return

            # 2. Upsert customer
            cust = await customer_model.get_or_create_customer(
                phone=msg.phone,
                name=msg.name,
                business_id=business.id,
                db=db,
            )

            if cust.ai_paused:
                logger.info(f"AI paused for customer={cust.id}. Skipping.")
                return

            # 3. Save incoming message + mark as read in parallel
            await asyncio.gather(
                conv_model.save_message(
                    db=db,
                    customer_id=cust.id,
                    business_id=business.id,
                    role="user",
                    content=msg.text,
                ),
                mark_as_read(msg.message_id),
            )

            # 4. Cancel pending follow-up (customer is active again)
            await cancel_followup(cust.id)

            # 5. Classify intent (fast, zero-cost)
            intent = classify_intent(msg.text)
            logger.info(f"[Pipeline] phone={msg.phone} intent={intent} text={msg.text[:60]!r}")

            # 6. Conversation history
            history = await conv_model.get_conversation_history(db, cust.id, limit=10)

            # 7. Reply Agent + Sales Agent in parallel (Sales only when relevant)
            needs_sales = intent in ("purchase", "price_inquiry")
            reply_agent = ReplyAgent(business_id=business.id)

            if needs_sales:
                sales_agent = SalesAgent(business_id=business.id)
                t_agents = time.monotonic()
                response_text, offer = await asyncio.gather(
                    reply_agent.run(
                        customer_message=msg.text,
                        history=history,
                        customer_name=cust.name,
                        intent=intent,
                    ),
                    sales_agent.get_offer(msg.text),
                )
                logger.info(
                    f"[Pipeline] parallel agents done in "
                    f"{(time.monotonic() - t_agents) * 1000:.0f}ms "
                    f"offer={'yes' if offer else 'no'}"
                )
                if offer:
                    response_text += f"\n\n{offer}"
            else:
                response_text = await reply_agent.run(
                    customer_message=msg.text,
                    history=history,
                    customer_name=cust.name,
                    intent=intent,
                )

            # 8. Send reply — with interactive buttons when intent warrants it
            await _send_reply(msg.phone, response_text, intent)

            # 9. Save AI response + upsert lead in parallel
            await asyncio.gather(
                conv_model.save_message(
                    db=db,
                    customer_id=cust.id,
                    business_id=business.id,
                    role="assistant",
                    content=response_text,
                ),
                lead_model.upsert_lead(
                    db=db,
                    customer_id=cust.id,
                    business_id=business.id,
                    intent=intent,
                ),
            )

            # 10. Schedule follow-up
            await schedule_followup(
                customer_id=cust.id,
                phone=msg.phone,
                intent=intent,
                followup_hours=business.followup_hours,
            )

            logger.info(
                f"[Pipeline] complete phone={msg.phone} "
                f"total={( time.monotonic() - t0) * 1000:.0f}ms"
            )

        except Exception as e:
            logger.error(f"[Pipeline] error for phone={msg.phone}: {e}", exc_info=True)


# ---------------------------------------------------------------------------
# Intent-based reply sender
# ---------------------------------------------------------------------------

_INTENT_BUTTONS = {
    "greeting": [
        {"id": "see_products",  "title": "🛍️ Products"},
        {"id": "check_offers",  "title": "🎁 Offers"},
        {"id": "contact_owner", "title": "📞 Contact"},
    ],
    "price_inquiry": [
        {"id": "order_now",     "title": "🛒 Order Now"},
        {"id": "see_more",      "title": "📋 See More"},
        {"id": "ask_question",  "title": "❓ Ask Question"},
    ],
    "purchase": [
        {"id": "confirm_order", "title": "✅ Confirm Order"},
        {"id": "change_item",   "title": "🔄 Change Item"},
        {"id": "cancel_order",  "title": "❌ Cancel"},
    ],
    "complaint": [
        {"id": "request_refund", "title": "🔄 Request Refund"},
        {"id": "call_owner",     "title": "📞 Call Owner"},
        {"id": "send_photo",     "title": "📸 Send Photo"},
    ],
}


async def _send_reply(phone: str, text: str, intent: str) -> None:
    """
    Send the AI reply with interactive buttons when the intent supports it.
    Falls back to plain text if button send fails.
    """
    buttons = _INTENT_BUTTONS.get(intent)
    if buttons:
        sent = await send_whatsapp_buttons(
            to_phone=phone,
            body=text,
            buttons=buttons,
        )
        if sent:
            return
        # Fallback to plain text if interactive send fails
        logger.warning(f"[Pipeline] Button send failed for intent={intent}, falling back to text")
    await send_whatsapp_message(phone, text)
