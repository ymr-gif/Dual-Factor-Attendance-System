# nfc-scan backend image (Step 10 — one-command setup).
# CPU-only. GPU (onnxruntime-gpu) is a later, host-specific concern (see CLAUDE.md).

# --- Frontend build stage (Step 12): build the SPA to /web/dist ---
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# --- Backend runtime stage ---
FROM python:3.11-slim

# OpenCV (opencv-python-headless) still needs libGL + glib at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY backend ./backend

# Built SPA from the web stage — backend serves it at /app if present.
COPY --from=web /web/dist ./frontend/dist

# Pin + fetch the MiniFASNet anti-spoof weights at build time (sha256-checked,
# ~3.4MB). Baked into the image so the container needs no network at first tap.
RUN python -m backend.fetch_liveness_models

# InsightFace buffalo_l still auto-downloads to ~/.insightface on first tap.
EXPOSE 8001
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
