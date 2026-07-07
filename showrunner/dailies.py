"""Dailies review — the agent watches its own footage.

Every generated clip gets screened by Qwen-VL against its shot brief; failed
takes (artifacts, wrong subject, broken scene) are reshot — selectively, within
a hard reshoot budget. This is the difference between a pipeline that renders
and a studio that checks its work.
"""

import base64
import subprocess
import tempfile
from pathlib import Path

from . import config
from .ledger import Ledger
from .llm import chat_vision_json

SYSTEM = """You are a film continuity supervisor reviewing a generated take.
You see 2 frames sampled from one clip, plus the shot brief it was generated from.
Reject the take ONLY for real production problems:
- heavy visual artifacts (warped faces/limbs, melting objects, garbled text)
- wrong subject or setting versus the brief
- broken scene (empty frame, glitch, unreadable image)
Minor style drift is acceptable. Reply ONLY JSON:
{"ok": bool, "reason": "short phrase, empty if ok"}"""


def _frames_b64(clip: Path) -> list[str]:
    """Two JPEG frames at ~20% and ~80% of the clip."""
    frames = []
    with tempfile.TemporaryDirectory() as td:
        for i, ts in enumerate((config.CLIP_SECONDS * 0.2, config.CLIP_SECONDS * 0.8)):
            out = Path(td) / f"f{i}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ts:.2f}",
                 "-i", str(clip), "-frames:v", "1", "-q:v", "4", str(out)],
                check=True)
            frames.append(base64.b64encode(out.read_bytes()).decode())
    return frames


def review_take(clip: Path, shot: dict, ledger: Ledger) -> dict:
    """One VL verdict for one clip. ~8s, fractions of a cent."""
    verdict = chat_vision_json(
        "dailies", config.MODEL_PLANNER, SYSTEM,
        f"Shot brief: {shot['prompt']}", _frames_b64(clip), ledger)
    return {"ok": bool(verdict.get("ok")),
            "reason": str(verdict.get("reason", ""))[:120]}
