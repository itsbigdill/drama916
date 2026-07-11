#!/usr/bin/env bash
# Build drama916-fc.zip — a Function Compute code package for a Python 3.10
# Web Function (no container registry needed). Bundles: the app, Linux-x86_64
# python deps, static ffmpeg/ffprobe, the seeded showcase films, and a bootstrap
# that runs the server on FC ($PORT, /tmp for writes since the code dir is
# read-only). Upload the result via OSS (it's ~145M, over FC's 100M direct limit).
set -euo pipefail
cd "$(dirname "$0")"

FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
PYVER=3.10   # must match the FC runtime (Python 3.10 web function)

rm -rf fc-build && mkdir -p fc-build/code
cd fc-build

echo "==> 1/4  vendoring python deps for linux x86_64 / cp${PYVER/./}"
python3 -m pip install \
  --target code \
  --platform manylinux2014_x86_64 \
  --python-version "$PYVER" \
  --only-binary=:all: --no-compile \
  openai httpx python-dotenv rich >/dev/null
rm -rf code/images   # tqdm ships demo gifs at the package root — drop the cruft

echo "==> 2/4  fetching static ffmpeg/ffprobe (amd64)"
curl -sL -o ffmpeg.tar.xz "$FFMPEG_URL"
tar xf ffmpeg.tar.xz
D=$(ls -d ffmpeg-*-amd64-static | head -1)
mkdir -p code/bin && cp "$D/ffmpeg" "$D/ffprobe" code/bin/
rm -rf ffmpeg.tar.xz "$D"

echo "==> 3/4  app code + seeds + bootstrap"
cp ../web.py ../main.py code/
rsync -a --exclude='__pycache__' --exclude='*.pyc' ../showrunner code/
[ -d ../runs_seed ] || ../seed_showcase.sh
rm -rf code/runs_seed && mkdir -p code/runs_seed && cp -r ../runs_seed/* code/runs_seed/
cat > code/bootstrap <<'SH'
#!/bin/bash
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HERE/bin:$PATH"        # bundled static ffmpeg/ffprobe
export RUNS_DIR="/tmp/runs"          # FC code dir is read-only; /tmp is writable
export PORT="${FC_SERVER_PORT:-9000}"
mkdir -p "$RUNS_DIR"
cp -rn "$HERE/runs_seed/." "$RUNS_DIR/" 2>/dev/null || true   # seed the rail once
cd "$HERE"
exec python3 web.py
SH
chmod +x code/bootstrap code/bin/ffmpeg code/bin/ffprobe

echo "==> 4/4  zipping"
rm -f drama916-fc.zip
( cd code && zip -qr -X ../drama916-fc.zip . -x '*.DS_Store' '*/__pycache__/*' )
echo "built fc-build/drama916-fc.zip ($(du -h drama916-fc.zip | cut -f1))"
