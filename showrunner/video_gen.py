"""HappyHorse text-to-video via DashScope async task API (intl region).

Docs: https://www.alibabacloud.com/help/en/model-studio/ (video generation).
Flow: POST task with X-DashScope-Async: enable -> poll GET /tasks/{id} -> download MP4.
"""

import os
import subprocess
import time
from pathlib import Path

import httpx

from . import config
from .ledger import Ledger

CREATE_URL = f"{config.DASHSCOPE_API_BASE}/api/v1/services/aigc/video-generation/video-synthesis"
TASK_URL = f"{config.DASHSCOPE_API_BASE}/api/v1/tasks/{{task_id}}"


def _headers():
    return {"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
            "X-DashScope-Async": "enable", "Content-Type": "application/json"}


def generate_clip(shot: dict, out_path: Path, ledger: Ledger, dry_run: bool) -> Path:
    if dry_run:
        _placeholder_clip(shot, out_path)
        ledger.record("video_dryrun", config.MODEL_VIDEO)
        return out_path

    body = {"model": config.MODEL_VIDEO,
            "input": {"prompt": shot["prompt"]},
            "parameters": {"size": config.VIDEO_SIZE, "duration": config.CLIP_SECONDS}}
    r = httpx.post(CREATE_URL, json=body, headers=_headers(), timeout=60)
    r.raise_for_status()
    task_id = r.json()["output"]["task_id"]

    while True:  # poll until done; HappyHorse tasks take ~1-5 min
        time.sleep(15)
        s = httpx.get(TASK_URL.format(task_id=task_id),
                      headers={"Authorization": _headers()["Authorization"]}, timeout=60)
        s.raise_for_status()
        out = s.json()["output"]
        status = out["task_status"]
        if status == "SUCCEEDED":
            video_url = out["video_url"]
            break
        if status in ("FAILED", "CANCELED"):
            raise RuntimeError(f"shot {shot['id']} failed: {out}")

    with httpx.stream("GET", video_url, timeout=300) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    ledger.record("video", config.MODEL_VIDEO, clips=1, clip_cost=config.COST_PER_CLIP_USD)
    return out_path


def _placeholder_clip(shot: dict, out_path: Path):
    """ffmpeg color card with the shot id — full pipeline testable for $0."""
    label = f"shot {shot['id']}"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i",
         f"color=c=0x22333b:s=1280x720:d={config.CLIP_SECONDS}",
         "-vf", f"drawtext=text='{label}':fontsize=64:fontcolor=white:"
                "x=(w-text_w)/2:y=(h-text_h)/2",
         "-pix_fmt", "yuv420p", str(out_path)],
        check=True)
