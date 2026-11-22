# Stage 1: build the static frontend. Node is not included in the final image.
FROM node:22-alpine AS web
WORKDIR /web
COPY app/package.json app/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/ ./
RUN npm run build

# Stage 2: API plus the built frontend in one small service.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY config/ config/
COPY api/ api/
COPY scripts/ scripts/
COPY models/ models/
COPY --from=web /web/dist app/dist

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p data/app \
    && chown -R appuser:appuser data
USER appuser

# The database lives here; mount a volume so it survives container replacement.
VOLUME ["/app/data/app"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/ready', timeout=4)"]

# FLOWTOOL_SECRET_KEY must be supplied at runtime; the API refuses to start without it.
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
