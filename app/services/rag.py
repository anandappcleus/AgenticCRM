import chromadb
import logging
from typing import List
from openai import AsyncOpenAI
from app.config import settings
from app.services.redis_client import get_cached_embedding, set_cached_embedding

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)


class BusinessRAG:
    """
    Per-business ChromaDB collection for product catalog + FAQs.
    Each business gets its own isolated collection.
    """

    def __init__(self, business_id: str):
        self.business_id = business_id
        self.chroma = chromadb.PersistentClient(path=settings.CHROMA_PATH)
        self.collection = self.chroma.get_or_create_collection(
            name=f"business_{business_id}",
            metadata={"hnsw:space": "cosine"},
        )

    async def query(self, text: str, top_k: int = 4) -> str:
        """Retrieve the most relevant business knowledge for a customer query."""
        count = self.collection.count()
        if count == 0:
            logger.warning(f"[RAG] business={self.business_id} catalog is empty — replying generically")
            return "No business knowledge loaded yet. Reply generically."

        extra: dict = {}
        if settings.OPENAI_EMBED_QUERY_TYPE:
            extra["input_type"] = settings.OPENAI_EMBED_QUERY_TYPE

        # Check Redis cache before calling NIM
        query_embedding = await get_cached_embedding(settings.OPENAI_EMBED_MODEL, text)
        if query_embedding:
            logger.info(f"[RAG] embedding cache HIT for business={self.business_id}")
        else:
            try:
                embed_resp = await client.embeddings.create(
                    input=text,
                    model=settings.OPENAI_EMBED_MODEL,
                    extra_body=extra or None,
                )
            except Exception as e:
                logger.error(f"[RAG] Embedding failed for business={self.business_id}: {e}", exc_info=True)
                return "No business knowledge loaded yet. Reply generically."
            query_embedding = embed_resp.data[0].embedding
            await set_cached_embedding(settings.OPENAI_EMBED_MODEL, text, query_embedding)

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, count),
            )
            docs = results["documents"][0]
        except Exception as e:
            logger.error(f"[RAG] ChromaDB query failed for business={self.business_id}: {e}", exc_info=True)
            return "No business knowledge loaded yet. Reply generically."

        if not docs:
            logger.warning(f"[RAG] business={self.business_id} query returned 0 results for: {text[:60]}")
            return "No business knowledge loaded yet. Reply generically."

        logger.info(f"[RAG] business={self.business_id} retrieved {len(docs)} results for: {text[:60]}")
        return "\n---\n".join(docs)

    async def ingest_catalog(self, items: List[dict]) -> dict:
        """
        Index a product catalog or FAQ list into ChromaDB.
        Each item must have: name, price, description.
        Optional: category, available.
        """
        texts, ids, metas = [], [], []

        for i, item in enumerate(items):
            text = (
                f"Product: {item['name']}\n"
                f"Price: ₹{item['price']}\n"
                f"Description: {item['description']}\n"
                f"Category: {item.get('category', 'General')}\n"
                f"Available: {item.get('available', True)}"
            )
            texts.append(text)
            ids.append(f"{self.business_id}_{i}")
            metas.append({"type": "product", "name": item["name"]})

        # Batch embed all texts in one API call
        extra: dict = {}
        if settings.OPENAI_EMBED_PASSAGE_TYPE:
            extra["input_type"] = settings.OPENAI_EMBED_PASSAGE_TYPE
        try:
            embed_resp = await client.embeddings.create(
                input=texts,
                model=settings.OPENAI_EMBED_MODEL,
                extra_body=extra or None,
            )
        except Exception as e:
            logger.error(f"[RAG] Catalog embedding failed for business={self.business_id}: {e}", exc_info=True)
            raise

        embeddings = [d.embedding for d in embed_resp.data]

        try:
            self.collection.upsert(
                documents=texts,
                embeddings=embeddings,
                ids=ids,
                metadatas=metas,
            )
        except Exception as e:
            logger.error(f"[RAG] ChromaDB upsert failed for business={self.business_id}: {e}", exc_info=True)
            raise

        logger.info(f"[RAG] Ingested {len(texts)} items for business={self.business_id}")
        return {"ingested": len(texts)}
