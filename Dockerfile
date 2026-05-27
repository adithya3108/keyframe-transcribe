FROM python:3.11-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps — CPU-only torch first (smaller image)
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data dir (Railway mounts a persistent volume here)
RUN mkdir -p /data/cache/transcripts
ENV CACHE_DIR=/data/cache

EXPOSE 8000

COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

CMD ["/startup.sh"]
