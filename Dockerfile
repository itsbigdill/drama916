# drama916 — one logline in, a voiced vertical drama out.
# Self-contained image: Python + ffmpeg + the app. Only secret is DASHSCOPE_API_KEY.
FROM python:3.12-slim

# ffmpeg/ffprobe drive the cut (crossfades, voice mixing, dailies probing)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# deps first so the layer caches across code edits
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# app code (runs/ and .venv are excluded via .dockerignore)
COPY showrunner ./showrunner
COPY web.py main.py README.md ./
# curated finished films so the "Recent generations" rail isn't empty on first
# load (public: owner.txt stripped by seed_showcase.sh). New runs write here too.
COPY runs_seed ./runs

# hosts inject PORT; FC custom-container defaults its listen port to 9000
ENV PORT=9000
EXPOSE 9000

# a shallow health signal for the platform's probe
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"9000\")}/status', timeout=3)" || exit 1

CMD ["python", "web.py"]
