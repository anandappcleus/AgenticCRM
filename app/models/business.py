import uuid
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.database import Business


async def create_business(
    db: AsyncSession,
    name: str,
    phone_number: str,
    whatsapp_phone_id: str,
    business_type: str,
    owner_email: str,
    language: str = "hinglish",
    followup_hours: int = 24,
    whatsapp_token: str = None,
    webhook_verify_token: str = None,
    system_prompt: str = None,
    business_hours: str = None,
) -> Tuple[Business, bool]:
    """Returns (business, created). created=False when record already existed."""
    business = Business(
        name=name,
        phone_number=phone_number,
        whatsapp_phone_id=whatsapp_phone_id,
        business_type=business_type,
        owner_email=owner_email,
        language=language,
        followup_hours=followup_hours,
        whatsapp_token=whatsapp_token,
        webhook_verify_token=webhook_verify_token,
        system_prompt=system_prompt,
        business_hours=business_hours,
    )
    db.add(business)
    try:
        await db.commit()
        await db.refresh(business)
        return business, True
    except IntegrityError:
        await db.rollback()
        existing = await db.execute(
            select(Business).where(Business.phone_number == phone_number)
        )
        return existing.scalar_one(), False


async def get_business_by_phone_id(
    db: AsyncSession, whatsapp_phone_id: str
) -> Optional[Business]:
    result = await db.execute(
        select(Business).where(Business.whatsapp_phone_id == whatsapp_phone_id)
    )
    return result.scalar_one_or_none()


async def get_business(db: AsyncSession, business_id: str) -> Optional[Business]:
    result = await db.execute(
        select(Business).where(Business.id == business_id)
    )
    return result.scalar_one_or_none()
