# ==============================================================================
# Production Dockerfile for Python Spotify Discord Music Bot
# ==============================================================================

FROM python:3.12-slim-bookworm

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies: FFmpeg, libopus, and SSL certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source code
COPY . .

# Create volume directories and assign permissions to non-root user
RUN mkdir -p /app/data /app/logs && \
    useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

VOLUME ["/app/data", "/app/logs"]

CMD ["python", "main.py"]

