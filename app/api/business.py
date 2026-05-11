import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.business import create_business, get_business
from app.services.rag import BusinessRAG, get_rag
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


async def _require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """Reject requests with a wrong key when API_KEY is configured in settings."""
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


class BusinessCreate(BaseModel):
    name: str
    phone_number: str
    whatsapp_phone_id: str
    business_type: str
    owner_email: str
    language: str = "hinglish"
    followup_hours: int = 24
    # Per-tenant credentials (optional — falls back to env vars when not set)
    whatsapp_token: Optional[str] = None
    webhook_verify_token: Optional[str] = None
    # Per-tenant AI customisation (optional)
    # Use {rag_context} and {customer_name} as placeholders in system_prompt
    system_prompt: Optional[str] = None
    # JSON string: {"mon": "10:00-20:00", "sun": "closed"} — None = always on
    business_hours: Optional[str] = None


class CatalogItem(BaseModel):
    name: str
    price: float
    description: str
    category: str = "General"
    available: bool = True


class CatalogUpload(BaseModel):
    business_id: str
    items: List[CatalogItem]


@router.post("/register", dependencies=[Depends(_require_api_key)])
async def register_business(
    body: BusinessCreate,
    db: AsyncSession = Depends(get_db),
):
    """Onboard a new SME client. Idempotent — returns existing record if phone already registered."""
    business, created = await create_business(
        db=db,
        name=body.name,
        phone_number=body.phone_number,
        whatsapp_phone_id=body.whatsapp_phone_id,
        business_type=body.business_type,
        owner_email=body.owner_email,
        language=body.language,
        followup_hours=body.followup_hours,
        whatsapp_token=body.whatsapp_token,
        webhook_verify_token=body.webhook_verify_token,
        system_prompt=body.system_prompt,
        business_hours=body.business_hours,
    )
    if created:
        logger.info(f"[Business] Registered new business id={business.id} name={business.name} phone={body.phone_number}")
    else:
        logger.info(f"[Business] Existing business returned id={business.id} name={business.name}")
    return {
        "id": business.id,
        "name": business.name,
        "message": "Business registered successfully" if created else "Business already exists",
    }


@router.post("/catalog", dependencies=[Depends(_require_api_key)])
async def upload_catalog(body: CatalogUpload):
    """Upload product catalog / FAQs — indexes into ChromaDB for RAG."""
    if not body.items:
        logger.warning(f"[Business] Catalog upload called with 0 items for business={body.business_id}")
        raise HTTPException(status_code=400, detail="items list cannot be empty")
    logger.info(f"[Business] Catalog upload started business={body.business_id} count={len(body.items)}")
    try:
        rag = get_rag(body.business_id)
        items = [item.model_dump() for item in body.items]
        result = await rag.ingest_catalog(items)
    except Exception as e:
        logger.error(f"[Business] Catalog upload FAILED business={body.business_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Catalog ingestion failed")
    logger.info(f"[Business] Catalog upload complete business={body.business_id} ingested={result['ingested']}")
    return {"status": "ok", "ingested": result["ingested"]}


@router.get("/{business_id}")
async def get_business_info(
    business_id: str,
    db: AsyncSession = Depends(get_db),
):
    business = await get_business(db, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return {
        "id": business.id,
        "name": business.name,
        "phone_number": business.phone_number,
        "business_type": business.business_type,
        "language": business.language,
        "ai_active": business.ai_active,
        "followup_hours": business.followup_hours,
    }
