# ---- stage 1: build the React dashboard ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- stage 2: engine runtime with pre-baked model weights ----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/models \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# bake model weights into the image so the first run never downloads them
RUN python -c "\
from huggingface_hub import snapshot_download;\
snapshot_download('ahmedrachid/FinancialBERT-Sentiment-Analysis');\
snapshot_download('typeform/distilbert-base-uncased-mnli')\
"

COPY src/ src/
COPY data/seed/ data/seed/
COPY data/portfolio/ data/portfolio/
COPY pyproject.toml ./
COPY --from=web /web/dist/ frontend/dist/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "src.engine.main:app", "--host", "0.0.0.0", "--port", "8000"]
