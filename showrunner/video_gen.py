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


def generate_clip(shot: dict, out_path: Path, ledger: Ledger, dry_run: bool,
                  size: str = config.VIDEO_SIZE,
                  first_frame: Path | None = None, _retry: bool = False) -> Path:
    if dry_run:
        _placeholder_clip(shot, out_path, size)
        ledger.record("video_dryrun", config.MODEL_VIDEO)
        return out_path

    if first_frame is not None and first_frame.exists():
        # i2v: the human-approved storyboard still IS the first frame of the clip —
        # the pixels you greenlit are the pixels that come alive. Size is derived
        # from the image (and upscaled to 1080p by the model), so no size param.
        from .storyboard import data_uri
        body = {"model": config.MODEL_VIDEO_I2V,
                "input": {"prompt": shot["prompt"],
                          "media": [{"type": "first_frame", "url": data_uri(first_frame)}]},
                "parameters": {"duration": config.CLIP_SECONDS}}
    else:
        body = {"model": config.MODEL_VIDEO,
                "input": {"prompt": shot["prompt"]},
                "parameters": {"size": size, "duration": config.CLIP_SECONDS}}
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
    tier = "1080" if body["model"] == config.MODEL_VIDEO_I2V else "720"
    ledger.record("video", body["model"], clips=1,
                  clip_cost=config.CLIP_SECONDS * config.VIDEO_RATE_PER_SEC[tier])

    # HappyHorse's output moderation sometimes returns SUCCEEDED with an all-black
    # video instead of FAILED — which then gets cut into the film as a black hole
    # (seen live: a hand-tap networking shot). Detect it and retry ONCE with a
    # sanitized prompt; still black → honest failure, never a silent fallback.
    if _is_black(out_path):
        if _retry:
            raise RuntimeError(
                f"shot {shot['id']}: HappyHorse returned a black video twice "
                f"(output moderation) — rewrite the shot's action and refilm")
        from .storyboard import _sanitized
        soft = dict(shot)
        soft["prompt"] = _sanitized(shot["prompt"], ledger)
        print(f"  shot {shot['id']}: black video from the model — retrying with softened prompt")
        return generate_clip(soft, out_path, ledger, dry_run, size=size,
                             first_frame=first_frame, _retry=True)
    return out_path


def _is_black(clip: Path, luma_threshold: float = 24.0, share: float = 0.85) -> bool:
    """True when ≥`share` of the clip is essentially black (mean luma below
    threshold). Uses ffmpeg blackdetect — local, free, ~a second."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(clip),
             "-vf", f"blackdetect=d=0.1:pix_th={luma_threshold / 255:.3f}",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120)
        import re as _re
        black = sum(float(m) for m in _re.findall(r"black_duration:([\d.]+)", r.stderr))
        dur_m = _re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        if not dur_m:
            return False
        h, m_, s = float(dur_m.group(1)), float(dur_m.group(2)), float(dur_m.group(3))
        total = h * 3600 + m_ * 60 + s
        return total > 0 and black / total >= share
    except Exception:
        return False  # детектор не має вбивати нормальний кліп


def _placeholder_clip(shot: dict, out_path: Path, size: str = config.VIDEO_SIZE):
    """ffmpeg color card with the shot id — full pipeline testable for $0."""
    label = f"shot {shot['id']}"
    wh = size.replace("*", "x")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i",
         f"color=c=0x22333b:s={wh}:d={config.CLIP_SECONDS}",
         "-vf", f"drawtext=text='{label}':fontsize=64:fontcolor=white:"
                "x=(w-text_w)/2:y=(h-text_h)/2",
         "-pix_fmt", "yuv420p", str(out_path)],
        check=True)
