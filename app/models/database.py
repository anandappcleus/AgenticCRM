import uuid
from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, Float,
    ForeignKey, Enum, func, JSON,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.config import settings

Base = declarative_base()

# Railway injects postgresql:// but asyncpg needs postgresql+asyncpg://
_db_url = settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://", 1
).replace(
    "postgres://", "postgresql+asyncpg://", 1  # older Railway format
)
engine = create_async_engine(_db_url, echo=settings.DEBUG)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── BUSINESS (one per client you onboard) ─────────────────────────────────
class Business(Base):
    __tablename__ = "businesses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False)
    phone_number = Column(String(20), unique=True)
    whatsapp_phone_id = Column(String(100))      # Meta phone number ID
    whatsapp_token = Column(Text, nullable=True)  # per-tenant token (overrides env)
    webhook_verify_token = Column(String(100), nullable=True)  # per-tenant verify token
    business_type = Column(String(50))            # clothing / salon / restaurant
    language = Column(String(20), default="hinglish")
    ai_active = Column(Boolean, default=True)
    followup_hours = Column(Integer, default=24)
    owner_email = Column(String(200))
    # Per-tenant AI persona — overrides default system prompt when set
    system_prompt = Column(Text, nullable=True)
    # Operating hours JSON: {"mon": "10:00-20:00", "sun": "closed"} — None = always on
    business_hours = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    customers = relationship("Customer", back_populates="business")


# ── CUSTOMER ──────────────────────────────────────────────────────────────
class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    business_id = Column(String, ForeignKey("businesses.id"), index=True)
    phone = Column(String(20), nullable=False)
    name = Column(String(200), default="Customer")
    ai_paused = Column(Boolean, default=False)   # owner took over
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now())
    total_messages = Column(Integer, default=0)

    business = relationship("Business", back_populates="customers")
    messages = relationship("Message", back_populates="customer")
    lead = relationship("Lead", back_populates="customer", uselist=False)
    orders = relationship("Order", back_populates="customer")


# ── MESSAGE ───────────────────────────────────────────────────────────────
class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customers.id"), index=True)
    business_id = Column(String, ForeignKey("businesses.id"))
    role = Column(Enum("user", "assistant", name="role_enum"), nullable=False)
    content = Column(Text, nullable=False)
    is_manual = Column(Boolean, default=False)  # owner sent manually?
    created_at = Column(DateTime, default=func.now())

    customer = relationship("Customer", back_populates="messages")


# ── LEAD ──────────────────────────────────────────────────────────────────
class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customers.id"), unique=True)
    business_id = Column(String, ForeignKey("businesses.id"), index=True)
    status = Column(
        Enum("hot", "warm", "cold", name="lead_status"), default="warm"
    )
    intent = Column(String(50))
    score = Column(Integer, default=50)           # 0–100
    followup_scheduled = Column(Boolean, default=False)
    followup_sent_at = Column(DateTime, nullable=True)
    converted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    customer = relationship("Customer", back_populates="lead")


# ── ORDER ─────────────────────────────────────────────────────────────────
class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customers.id"), index=True)
    business_id = Column(String, ForeignKey("businesses.id"), index=True)
    status = Column(
        Enum("pending", "confirmed", "processing", "shipped", "delivered", "cancelled",
             name="order_status"),
        default="pending",
    )
    total_amount = Column(Float, default=0.0)
    delivery_address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


# ── ORDER ITEM ────────────────────────────────────────────────────────────
class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String, ForeignKey("orders.id"), index=True)
    product_name = Column(String(200), nullable=False)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
