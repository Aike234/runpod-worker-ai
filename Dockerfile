# ============================================================
# Iyke Movie Studio — Runpod GPU Worker
# Dockerfile for AI Video Production
# ============================================================
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

# System dependencies: FFmpeg + audio tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    curl \
    wget \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy worker code
COPY handler.py .
COPY pipeline/ ./pipeline/

# Pre-create output and model cache dirs
RUN mkdir -p /app/output /app/models /app/cache /app/logs /app/tmp

# Environment defaults (overridden at runtime)
ENV PYTHONUNBUFFERED=1
ENV OUTPUT_DIR=/app/output
ENV MODELS_DIR=/app/models
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Runpod entrypoint
CMD [ python, -u, handler.py]
