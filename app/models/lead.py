from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.database import Lead

# Intent → lead status + score mapping
INTENT_LEAD_MAP = {
    "purchase":      {"status": "hot",  "score": 90},
    "price_inquiry": {"status": "warm", "score": 70},
    "general":       {"status": "warm", "score": 50},
    "hours":         {"status": "warm", "score": 45},
    "greeting":      {"status": "cold", "score": 20},
    "complaint":     {"status": "warm", "score": 40},
}


async def upsert_lead(
    db: AsyncSession, customer_id: str, business_id: str, intent: str
) -> Lead:
    """Create or update a lead record based on latest intent."""
    result = await db.execute(
        select(Lead).where(Lead.customer_id == customer_id)
    )
    lead = result.scalar_one_or_none()
    mapping = INTENT_LEAD_MAP.get(intent, {"status": "warm", "score": 50})

    if lead is None:
        lead = Lead(
            customer_id=customer_id,
            business_id=business_id,
            intent=intent,
            status=mapping["status"],
            score=mapping["score"],
        )
        db.add(lead)
    else:
        # Only upgrade status, never downgrade in a single message
        if mapping["score"] > lead.score:
            lead.status = mapping["status"]
            lead.score = mapping["score"]
        lead.intent = intent

    await db.commit()
    await db.refresh(lead)
    return lead


async def count_by_status(
    db: AsyncSession, business_id: str, status: str
) -> int:
    result = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.business_id == business_id,
            Lead.status == status,
        )
    )
    return result.scalar_one()


async def count_pending_followups(db: AsyncSession, business_id: str) -> int:
    result = await db.execute(
        select(func.count(Lead.id)).where(
            Lead.business_id == business_id,
            Lead.followup_scheduled == True,  # noqa: E712
        )
    )
    return result.scalar_one()


async def get_leads(
    db: AsyncSession, business_id: str, status: str = "all"
) -> List[dict]:
    query = select(Lead).where(Lead.business_id == business_id)
    if status != "all":
        query = query.where(Lead.status == status)
    query = query.order_by(Lead.score.desc())

    result = await db.execute(query)
    leads = result.scalars().all()
    return [
        {
            "id": l.id,
            "customer_id": l.customer_id,
            "status": l.status,
            "intent": l.intent,
            "score": l.score,
            "followup_scheduled": l.followup_scheduled,
            "converted": l.converted,
            "updated_at": l.updated_at.isoformat() if l.updated_at else None,
        }
        for l in leads
    ]
