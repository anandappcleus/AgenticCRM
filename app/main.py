from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import webhook, dashboard, business
from app.models.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.redis_client import init_redis, close_redis
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting WhatsApp CRM...")
    await init_db()
    await init_redis(settings.REDIS_URL)
    start_scheduler()
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
