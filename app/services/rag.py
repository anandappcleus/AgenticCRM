import chromadb
import logging
from typing import List
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


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
        if self.collection.count() == 0:
            return "No business knowledge loaded yet. Reply generically."

        embed_resp = await client.embeddings.create(
            input=text,
            model=settings.OPENAI_EMBED_MODEL,
        )
        query_embedding = embed_resp.data[0].embedding

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count()),
        )
        docs = results["documents"][0]
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
        embed_resp = await client.embeddings.create(
            input=texts,
            model=settings.OPENAI_EMBED_MODEL,
        )
        embeddings = [d.embedding for d in embed_resp.data]

        self.collection.upsert(
            documents=texts,
            embeddings=embeddings,
            ids=ids,
            metadatas=metas,
        )
        logger.info(
            f"Ingested {len(texts)} items for business {self.business_id}"
        )
        return {"ingested": len(texts)}
