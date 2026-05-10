from datetime import datetime, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from app.models.database import Message


async def save_message(
    db: AsyncSession,
    customer_id: str,
    business_id: str,
    role: str,
    content: str,
    is_manual: bool = False,
) -> Message:
    msg = Message(
        customer_id=customer_id,
        business_id=business_id,
        role=role,
        content=content,
        is_manual=is_manual,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_conversation_history(
    db: AsyncSession, customer_id: str, limit: int = 10
) -> List[dict]:
    """Return last N messages as OpenAI-compatible dicts (role + content)."""
    result = await db.execute(
        select(Message)
        .where(Message.customer_id == customer_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    # Reverse so oldest first (correct order for OpenAI context)
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]


async def get_full_history(db: AsyncSession, customer_id: str) -> List[dict]:
    """Return all messages for a customer (for iOS chat view)."""
    result = await db.execute(
        select(Message)
        .where(Message.customer_id == customer_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "is_manual": m.is_manual,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


async def count_today(db: AsyncSession, business_id: str) -> int:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.business_id == business_id,
            Message.created_at >= today_start,
        )
    )
    return result.scalar_one()
