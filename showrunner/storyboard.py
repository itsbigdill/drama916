"""Visual storyboard — a still frame per shot, drawn before any video is filmed.

The human approves PICTURES, not prompts. Stills are cheap (~12s, cents) and
they double as the visual anchor for image-to-video continuity later.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import httpx

from . import config
from .ledger import Ledger

URL = f"{config.DASHSCOPE_API_BASE}/api/v1/services/aigc/multimodal-generation/generation"


def generate_still(prompt: str, size: str, out_path: Path, ledger: Ledger) -> Path:
    r = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": config.MODEL_IMAGE,
              "input": {"messages": [{"role": "user", "content": [
                  {"text": f"Storyboard frame, cinematic still: {prompt}"}]}]},
              "parameters": {"size": size, "n": 1}},
        timeout=120)
    r.raise_for_status()
    content = r.json()["output"]["choices"][0]["message"]["content"]
    image_url = next(c["image"] for c in content if "image" in c)
    img = httpx.get(image_url, timeout=120)
    img.raise_for_status()
    out_path.write_bytes(img.content)
    ledger.record("stills", config.MODEL_IMAGE, clips=1,
                  clip_cost=config.COST_PER_STILL_USD)
    return out_path


def sketch_all(shots: list[dict], size: str, board_dir: Path, ledger: Ledger,
               progress: Callable[[int, int], None]) -> list[Path]:
    board_dir.mkdir(parents=True, exist_ok=True)
    done = 0

    def one(shot: dict) -> Path | None:
        nonlocal done
        out = board_dir / f"shot_{shot['id']:02}.png"
        try:
            generate_still(shot["prompt"], size, out, ledger)
        except Exception:
            out = None  # board falls back to text for this shot; never kills the run
        done += 1
        progress(done, len(shots))
        return out

    with ThreadPoolExecutor(max_workers=config.CONCURRENT_CLIPS) as pool:
        return list(pool.map(one, shots))
