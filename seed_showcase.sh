#!/usr/bin/env bash
# Build runs_seed/ — a curated set of finished films baked into the image so the
# "Recent generations" rail is alive on first load. Only the files /videos needs
# are copied, and owner.txt is dropped so the films are public to every visitor.
set -euo pipefail
cd "$(dirname "$0")"

SHOWCASE=(
  "0710-212754"  # Gods of the Pitch
  "0710-185859"  # Burger Ball
  "0707-144459"  # Kung Fu Kickoff
  "0710-162444"  # Forbidden Fruit
)

rm -rf runs_seed
for id in "${SHOWCASE[@]}"; do
  src="runs/$id"
  dst="runs_seed/$id"
  [ -f "$src/final.mp4" ] || { echo "skip $id (no final.mp4)"; continue; }
  mkdir -p "$dst/board"
  cp "$src/final.mp4"            "$dst/"
  cp "$src/caption.txt"         "$dst/" 2>/dev/null || true
  cp "$src/screenplay.json"     "$dst/" 2>/dev/null || true
  cp "$src/run_report.json"     "$dst/" 2>/dev/null || true
  cp "$src/board/shot_01.png"   "$dst/board/" 2>/dev/null || true
  # public showcase → no owner gating
  rm -f "$dst/owner.txt"
  echo "seeded $id"
done
echo "runs_seed size: $(du -sh runs_seed | cut -f1)"
