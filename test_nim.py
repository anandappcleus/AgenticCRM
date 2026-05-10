"""Quick NIM validation test. Run: python3 test_nim.py"""
import asyncio, math
from openai import AsyncOpenAI
from app.config import settings

async def test_chat():
    print("\n── Chat Test (" + settings.OPENAI_MODEL + ") ──")
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    resp = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a WhatsApp assistant for a clothing shop in India. Reply in Hinglish. Short and warm."},
            {"role": "user", "content": "Bhaiya jacket ka price kya hai?"},
        ],
        max_tokens=150,
        temperature=0.7,
    )
    print(f"Reply : {resp.choices[0].message.content.strip()}")
    print(f"Tokens: {resp.usage.total_tokens}")

async def test_embeddings():
    print("\n── Embedding Test (" + settings.OPENAI_EMBED_MODEL + ") ──")
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    resp = await client.embeddings.create(
        model=settings.OPENAI_EMBED_MODEL,
        input=["Blue denim jacket size L", "Neeli jacket badi size mein"],
        extra_body={"input_type": settings.OPENAI_EMBED_PASSAGE_TYPE} if settings.OPENAI_EMBED_PASSAGE_TYPE else None,
    )
    dims = len(resp.data[0].embedding)
    match = "✅" if dims == settings.OPENAI_EMBED_DIMENSIONS else f"⚠️  Mismatch! Set OPENAI_EMBED_DIMENSIONS={dims} in .env"
    print(f"Dims  : {dims} (config: {settings.OPENAI_EMBED_DIMENSIONS}) {match}")
    v1, v2 = resp.data[0].embedding, resp.data[1].embedding
    dot = sum(a*b for a,b in zip(v1,v2))
    sim = dot / (math.sqrt(sum(a*a for a in v1)) * math.sqrt(sum(b*b for b in v2)))
    quality = "✅ good" if sim > 0.80 else "⚠️  low — model may not handle Hinglish well"
    print(f"Hindi↔Hinglish similarity: {sim:.3f} {quality}")

async def test_multiturn():
    print("\n── Multi-turn Hinglish Test ──")
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
    resp = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "Assistant for Anand Kapde Wale. Products: Blue Jacket Rs850, Red Kurti Rs450. Reply in Hinglish. Max 2 sentences."},
            {"role": "user", "content": "Jacket available hai?"},
            {"role": "assistant", "content": "Haan ji! Blue denim jacket available hai Rs850 mein"},
            {"role": "user", "content": "XL size milega?"},
        ],
        max_tokens=100,
        temperature=0.7,
    )
    print(f"Reply : {resp.choices[0].message.content.strip()}")

async def main():
    print("=" * 54)
    print("  NVIDIA NIM Validation — WhatsApp CRM")
    print(f"  Model : {settings.OPENAI_MODEL}")
    print(f"  Embed : {settings.OPENAI_EMBED_MODEL}")
    print(f"  URL   : {settings.OPENAI_BASE_URL}")
    print("=" * 54)
    if not settings.OPENAI_API_KEY or "your_" in settings.OPENAI_API_KEY:
        print("❌ Set OPENAI_API_KEY in .env first"); return
    ok = True
    for fn in [test_chat, test_embeddings, test_multiturn]:
        try:
            await fn()
        except Exception as e:
            print(f"❌ {fn.__name__} failed: {e}")
            ok = False
    print("\n" + "=" * 54)
    print("  ✅ All tests passed!" if ok else "  ❌ Some tests failed — check above")
    print("=" * 54)

asyncio.run(main())
