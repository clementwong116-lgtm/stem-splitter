# Stem Splitter PWA — ffmpeg mid/side fallback (no StemSplit key / Demucs required)
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Optional AI deps left out of image (torch/demucs are huge).
# Install via STEM_PROVIDER=demucs + larger image if needed later.
COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt || true

COPY app.py stemsplit_client.py start.sh ./
COPY static ./static
COPY templates ./templates

RUN mkdir -p data/uploads data/outputs \
 && chmod +x start.sh

ENV HOST=0.0.0.0 \
    PORT=8765 \
    STEM_PROVIDER=ffmpeg \
    PYTHONUNBUFFERED=1

EXPOSE 8765

# Platforms inject PORT; start.sh / app.py honor it.
CMD ["python", "app.py"]
