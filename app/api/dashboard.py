from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models import customer, conversation, lead
from app.services.whatsapp import send_whatsapp_message

router = APIRouter()


@router.get("/stats")
async def get_dashboard_stats(
    business_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Summary stats for the iOS dashboard home screen."""
    return {
        "total_customers": await customer.count_by_business(db, business_id),
        "total_conversations_today": await conversation.count_today(db, business_id),
        "hot_leads": await lead.count_by_status(db, business_id, "hot"),
        "warm_leads": await lead.count_by_status(db, business_id, "warm"),
        "pending_followups": await lead.count_pending_followups(db, business_id),
    }


@router.get("/customers")
async def list_customers(
    business_id: str,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    return await customer.get_paginated(db, business_id, page)


@router.get("/customers/{customer_id}/messages")
async def get_chat_history(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await conversation.get_full_history(db, customer_id)


@router.get("/leads")
async def list_leads(
    business_id: str,
    status: str = "all",
    db: AsyncSession = Depends(get_db),
):
    return await lead.get_leads(db, business_id, status)


@router.post("/manual-reply")
async def send_manual_reply(body: dict):
    """Owner sends a manual message from the iOS app, bypassing AI."""
    phone = body.get("phone", "")
    text = body.get("text", "")
    if not phone or not text:
        return {"sent": False, "error": "phone and text are required"}
    ok = await send_whatsapp_message(phone, text)
    return {"sent": ok}


@router.post("/pause-ai/{customer_id}")
async def pause_ai_for_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Owner takes over — AI stops auto-replying to this customer."""
    await customer.set_ai_paused(db, customer_id, paused=True)
    return {"paused": True}


@router.post("/resume-ai/{customer_id}")
async def resume_ai_for_customer(
    customer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Re-enable AI auto-replies for a customer."""
    await customer.set_ai_paused(db, customer_id, paused=False)
    return {"paused": False}
