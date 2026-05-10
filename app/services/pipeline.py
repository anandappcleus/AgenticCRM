import logging
from app.services.whatsapp import IncomingMessage, send_whatsapp_message, mark_as_read
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
      1. Resolve business from phone_id
      2. Upsert customer
      3. Save incoming message
      4. Cancel pending follow-up (they replied!)
      5. Classify intent (no LLM, keyword-based)
      6. Build conversation history
      7. Reply Agent → GPT-4o + RAG
      8. Sales Agent (if purchase / price intent)
      9. Send reply via WhatsApp
     10. Save AI response
     11. Update lead score + schedule follow-up
    """
    async with AsyncSessionLocal() as db:
        try:
            # 1. Resolve business
            business = await get_business_by_phone_id(db, msg.whatsapp_phone_id)
            if business is None:
                logger.warning(
                    f"No business found for phone_id {msg.whatsapp_phone_id}. "
                    "Register the business first via POST /api/v1/business/register"
                )
                return

            if not business.ai_active:
                logger.info(f"AI is disabled for business {business.id}. Skipping.")
                return

            # 2. Upsert customer
            cust = await customer_model.get_or_create_customer(
                phone=msg.phone,
                name=msg.name,
                business_id=business.id,
                db=db,
            )

            # Check if owner has paused AI for this customer
            if cust.ai_paused:
                logger.info(f"AI paused for customer {cust.id}. Skipping.")
                return

            # 3. Save incoming message
            await conv_model.save_message(
                db=db,
                customer_id=cust.id,
                business_id=business.id,
                role="user",
                content=msg.text,
            )

            # Mark as read (shows blue ticks)
            await mark_as_read(msg.message_id)

            # 4. Cancel any pending follow-up (customer is active again)
            await cancel_followup(cust.id)

            # 5. Classify intent (fast, zero-cost)
            intent = classify_intent(msg.text)
            logger.info(f"[{msg.phone}] Intent: {intent} | Text: {msg.text[:60]}")

            # 6. Conversation history (last 10 messages as OpenAI dicts)
            history = await conv_model.get_conversation_history(
                db, cust.id, limit=10
            )

            # 7. Reply Agent
            reply_agent = ReplyAgent(business_id=business.id)
            response_text = await reply_agent.run(
                customer_message=msg.text,
                history=history,
                customer_name=cust.name,
                intent=intent,
            )

            # 8. Sales Agent — append offer if purchase/price intent
            if intent in ("purchase", "price_inquiry"):
                sales_agent = SalesAgent(business_id=business.id)
                offer = await sales_agent.get_offer(msg.text)
                if offer:
                    response_text += f"\n\n{offer}"

            # 9. Send reply
            await send_whatsapp_message(msg.phone, response_text)

            # 10. Save AI response
            await conv_model.save_message(
                db=db,
                customer_id=cust.id,
                business_id=business.id,
                role="assistant",
                content=response_text,
            )

            # 11. Update lead + schedule follow-up
            await lead_model.upsert_lead(
                db=db,
                customer_id=cust.id,
                business_id=business.id,
                intent=intent,
            )
            await schedule_followup(
                customer_id=cust.id,
                phone=msg.phone,
                intent=intent,
                followup_hours=business.followup_hours,
            )

        except Exception as e:
            logger.error(
                f"Pipeline error for {msg.phone}: {e}", exc_info=True
            )
