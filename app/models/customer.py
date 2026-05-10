from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from app.models.database import Customer


async def get_or_create_customer(
    phone: str, name: str, business_id: str, db: AsyncSession
) -> Customer:
    """Return existing customer or create a new one."""
    result = await db.execute(
        select(Customer).where(
            Customer.phone == phone,
            Customer.business_id == business_id,
        )
    )
    customer = result.scalar_one_or_none()

    if customer is None:
        customer = Customer(phone=phone, name=name, business_id=business_id)
        db.add(customer)
        await db.commit()
        await db.refresh(customer)
    else:
        # Update name if we have a better one
        if name and name != "Customer" and customer.name != name:
            customer.name = name
            await db.commit()

    return customer


async def count_by_business(db: AsyncSession, business_id: str) -> int:
    result = await db.execute(
        select(func.count(Customer.id)).where(Customer.business_id == business_id)
    )
    return result.scalar_one()


async def get_paginated(
    db: AsyncSession, business_id: str, page: int = 1, page_size: int = 20
) -> List[dict]:
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Customer)
        .where(Customer.business_id == business_id)
        .order_by(Customer.last_seen.desc())
        .offset(offset)
        .limit(page_size)
    )
    customers = result.scalars().all()
    return [
        {
            "id": c.id,
            "phone": c.phone,
            "name": c.name,
            "ai_paused": c.ai_paused,
            "total_messages": c.total_messages,
            "first_seen": c.first_seen.isoformat() if c.first_seen else None,
            "last_seen": c.last_seen.isoformat() if c.last_seen else None,
        }
        for c in customers
    ]


async def set_ai_paused(db: AsyncSession, customer_id: str, paused: bool):
    await db.execute(
        update(Customer)
        .where(Customer.id == customer_id)
        .values(ai_paused=paused)
    )
    await db.commit()


async def is_ai_paused(db: AsyncSession, customer_id: str) -> bool:
    result = await db.execute(
        select(Customer.ai_paused).where(Customer.id == customer_id)
    )
    val = result.scalar_one_or_none()
    return val if val is not None else False
