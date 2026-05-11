from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import webhook, dashboard, business
from app.models.database import init_db, AsyncSessionLocal
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.redis_client import init_redis, close_redis
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default seed catalog — ingested on startup if ChromaDB collection is empty
# Edit this list to change the default products for newly deployed instances.
# ---------------------------------------------------------------------------
_SEED_CATALOG = [
    {"name": "Blue Denim Jacket",   "price": 850.0,  "description": "Stylish blue denim jacket sizes S/M/L/XL machine washable",           "category": "Jackets",  "available": True},
    {"name": "Red Cotton Kurti",    "price": 450.0,  "description": "Red cotton kurti ladies sizes XS-XXL festive wear",                    "category": "Kurti",    "available": True},
    {"name": "Black Formal Trouser","price": 650.0,  "description": "Black slim-fit formal trouser for men sizes 28-38",                    "category": "Trousers", "available": True},
    {"name": "White Linen Shirt",   "price": 550.0,  "description": "White breathable linen shirt summer full sleeves M/L/XL",              "category": "Shirts",   "available": True},
    {"name": "Printed Saree",       "price": 1200.0, "description": "Floral printed synthetic saree 5.5 metres with blouse piece",          "category": "Sarees",   "available": True},
]


async def _seed_catalogs_if_empty() -> None:
    """
    On startup, check every registered business.
    If a business's ChromaDB collection is empty (fresh container / new deploy),
    re-ingest the seed catalog automatically so RAG works immediately.
    """
    from sqlalchemy import text
    from app.services.rag import BusinessRAG

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT id FROM businesses"))
            business_ids = [row[0] for row in result.fetchall()]

        for bid in business_ids:
            rag = BusinessRAG(bid)
            if rag.collection.count() == 0:
                result = await rag.ingest_catalog(_SEED_CATALOG)
                logger.info(f"[Startup] Auto-seeded catalog for business={bid} ({result.get('ingested', 0)} items)")
            else:
                logger.info(f"[Startup] ChromaDB OK for business={bid} ({rag.collection.count()} items)")
    except Exception as exc:
        logger.warning(f"[Startup] Catalog seed skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting WhatsApp CRM...")
    await init_db()
    await init_redis(settings.REDIS_URL)
    start_scheduler()
    await _seed_catalogs_if_empty()
    logger.info("Ready.")
    yield
    # Shutdown
    stop_scheduler()
    await close_redis()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="WhatsApp CRM API",
    version="1.0.0",
    description="Agentic WhatsApp CRM for Indian SMEs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten to specific origins in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(webhook.router, prefix="/api/v1/webhook", tags=["WhatsApp"])
app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
app.include_router(business.router, prefix="/api/v1/business", tags=["Business"])


@app.get("/")
async def health():
    return {"status": "running", "service": "WhatsApp CRM"}
