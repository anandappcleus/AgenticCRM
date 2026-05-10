FROM python:3.11-slim

WORKDIR /app

# Install deps first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code (Railway injects env vars — no .env needed)
COPY . .

# Create ChromaDB persistence directory
RUN mkdir -p /app/chroma_db

EXPOSE 8000

# Railway sets PORT env var; fall back to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
