from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.database import Order, OrderItem


async def create_order(
    db: AsyncSession,
    customer_id: str,
    business_id: str,
    items: List[dict],
    delivery_address: Optional[str] = None,
    notes: Optional[str] = None,
) -> Order:
    """
    Create a confirmed order with line items.
    Each item: {"product_name": str, "quantity": int, "unit_price": float}
    """
    total = sum(float(i["unit_price"]) * int(i["quantity"]) for i in items)
    order = Order(
        customer_id=customer_id,
        business_id=business_id,
        status="confirmed",
        total_amount=total,
        delivery_address=delivery_address,
        notes=notes,
    )
    db.add(order)
    await db.flush()  # get order.id before adding items

    for item in items:
        qty = int(item["quantity"])
        price = float(item["unit_price"])
        db.add(OrderItem(
            order_id=order.id,
            product_name=item["product_name"],
            quantity=qty,
            unit_price=price,
            total_price=price * qty,
        ))

    await db.commit()
    await db.refresh(order)
    return order


async def get_latest_order(db: AsyncSession, customer_id: str) -> Optional[Order]:
    """Return the most recent order for a customer, with items eager-loaded."""
    result = await db.execute(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_orders_by_business(
    db: AsyncSession, business_id: str, limit: int = 50
) -> List[dict]:
    """Return recent orders for dashboard display."""
    result = await db.execute(
        select(Order)
        .where(Order.business_id == business_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    orders = result.scalars().all()
    return [
        {
            "id": o.id,
            "customer_id": o.customer_id,
            "status": o.status,
            "total_amount": o.total_amount,
            "delivery_address": o.delivery_address,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]
