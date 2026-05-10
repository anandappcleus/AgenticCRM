from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import get_db
from app.models.business import create_business, get_business
from app.services.rag import BusinessRAG

router = APIRouter()


class BusinessCreate(BaseModel):
    name: str
    phone_number: str
    whatsapp_phone_id: str
    business_type: str
    owner_email: str
    language: str = "hinglish"
    followup_hours: int = 24


class CatalogItem(BaseModel):
    name: str
    price: float
    description: str
    category: str = "General"
    available: bool = True


class CatalogUpload(BaseModel):
    business_id: str
    items: List[CatalogItem]


@router.post("/register")
async def register_business(
    body: BusinessCreate,
    db: AsyncSession = Depends(get_db),
):
    """Onboard a new SME client."""
    business = await create_business(
        db=db,
        name=body.name,
        phone_number=body.phone_number,
        whatsapp_phone_id=body.whatsapp_phone_id,
        business_type=body.business_type,
        owner_email=body.owner_email,
        language=body.language,
        followup_hours=body.followup_hours,
    )
    return {
        "id": business.id,
        "name": business.name,
        "message": "Business registered successfully",
    }


@router.post("/catalog")
async def upload_catalog(body: CatalogUpload):
    """Upload product catalog / FAQs — indexes into ChromaDB for RAG."""
    rag = BusinessRAG(body.business_id)
    items = [item.model_dump() for item in body.items]
    result = await rag.ingest_catalog(items)
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
