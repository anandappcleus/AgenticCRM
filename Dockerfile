FROM python:3.11-slim

WORKDIR /app

# Install deps first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Create ChromaDB persistence directory
RUN mkdir -p /app/chroma_db

# Run with production settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
