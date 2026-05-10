import logging
from datetime import datetime, timedelta
from openai import AsyncOpenAI
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.services.whatsapp import send_whatsapp_message

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
scheduler = AsyncIOScheduler()

# Intents that should trigger a follow-up
FOLLOWUP_INTENTS = {"purchase", "price_inquiry", "general"}


async def schedule_followup(
    customer_id: str,
    phone: str,
    intent: str,
    followup_hours: int = 24,
) -> None:
    """Schedule a follow-up message if the customer goes quiet."""
    if intent not in FOLLOWUP_INTENTS:
        return

    job_id = f"followup_{customer_id}"

    # Remove any existing job for this customer first
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    run_time = datetime.now() + timedelta(hours=followup_hours)
    scheduler.add_job(
        send_followup_message,
        trigger="date",
        run_date=run_time,
        args=[phone, intent],
        id=job_id,
        replace_existing=True,
    )
    logger.info(
        f"Follow-up scheduled for customer {customer_id} at {run_time.isoformat()}"
    )


async def cancel_followup(customer_id: str) -> None:
    """Cancel a pending follow-up when the customer replies (they're active)."""
    job_id = f"followup_{customer_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Cancelled follow-up for customer {customer_id}")


async def send_followup_message(phone: str, intent: str) -> None:
    """Generate a personalised follow-up via GPT-4o and send it."""
    try:
        prompt = (
            f"Write a short, warm WhatsApp follow-up message in Hinglish.\n"
            f"Context: Customer showed '{intent}' intent but went quiet.\n"
            f"Rules: Max 2 sentences. Friendly. Not pushy. End with a question.\n"
            f"Example: \"Namaste! Kya aap abhi bhi jacket mein interested hain? 😊\""
        )
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.8,
        )
        message = resp.choices[0].message.content.strip()
        await send_whatsapp_message(phone, message)
        logger.info(f"Follow-up sent to {phone}: {message[:60]}")
    except Exception as e:
        logger.error(f"Follow-up failed for {phone}: {e}", exc_info=True)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
