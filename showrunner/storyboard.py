"""Visual storyboard — a still frame per shot, drawn before any video is filmed.

The human approves PICTURES, not prompts. Stills are cheap (~12s, cents) and
they double as the visual anchor for image-to-video continuity later.
"""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import httpx

from . import config
from .ledger import Ledger

URL = f"{config.DASHSCOPE_API_BASE}/api/v1/services/aigc/multimodal-generation/generation"


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _generate(content: list[dict], size: str, out_path: Path, ledger: Ledger,
              stage: str) -> Path:
    r = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": config.MODEL_IMAGE,
              "input": {"messages": [{"role": "user", "content": content}]},
              "parameters": {"size": size, "n": 1}},
        timeout=120)
    r.raise_for_status()
    parts = r.json()["output"]["choices"][0]["message"]["content"]
    image_url = next(c["image"] for c in parts if "image" in c)
    img = httpx.get(image_url, timeout=120)
    img.raise_for_status()
    out_path.write_bytes(img.content)
    ledger.record(stage, config.MODEL_IMAGE, clips=1,
                  clip_cost=config.COST_PER_STILL_USD)
    return out_path


def generate_still(prompt: str, size: str, out_path: Path, ledger: Ledger,
                   refs: list[Path] | None = None) -> Path:
    """Shot still. With refs (character sheets) the model keeps the same faces —
    that's what makes stills consistent with each other AND with the film."""
    content: list[dict] = [{"image": data_uri(r)} for r in (refs or [])]
    lead = ("Keep the EXACT same character(s) as in the reference image(s) — same face, "
            "same outfit, same proportions. " if refs else "")
    content.append({"text": f"{lead}Storyboard frame, cinematic still: {prompt}"})
    return _generate(content, size, out_path, ledger, "stills")


def generate_portrait(character: dict, size: str, out_path: Path, ledger: Ledger) -> Path:
    """One canonical reference portrait per character (the 'character sheet')."""
    content = [{"text": "Character reference sheet, single character, full body, "
                        "front view, neutral studio background, even lighting: "
                        f"{character.get('name', '')} — {character.get('visual', '')}"}]
    return _generate(content, size, out_path, ledger, "cast_sheet")


def cast_all(characters: list[dict], size: str, cast_dir: Path, ledger: Ledger,
             progress: Callable[[int, int], None]) -> list[Path]:
    """Portraits for the whole cast, in parallel. Failures are logged and skipped."""
    cast_dir.mkdir(parents=True, exist_ok=True)
    done = 0

    def one(ch: dict) -> Path | None:
        nonlocal done
        safe = "".join(c for c in ch.get("name", "x") if c.isalnum()) or "x"
        out = cast_dir / f"{safe}.png"
        try:
            generate_portrait(ch, size, out, ledger)
        except Exception as e:
            detail = getattr(getattr(e, "response", None), "text", "") or str(e)
            print(f"[cast] portrait '{ch.get('name')}' failed: {detail[:200]}")
            out = None
        done += 1
        progress(done, len(characters))
        return out

    with ThreadPoolExecutor(max_workers=2) as pool:  # image QPS is tight
        return [p for p in pool.map(one, characters) if p]


def sketch_all(shots: list[dict], size: str, board_dir: Path, ledger: Ledger,
               progress: Callable[[int, int], None],
               refs: list[Path] | None = None) -> list[Path]:
    board_dir.mkdir(parents=True, exist_ok=True)
    done = 0

    def one(shot: dict) -> Path | None:
        nonlocal done
        out = board_dir / f"shot_{shot['id']:02}.png"
        # one retry (transient rate limits / timeouts); moderation refusals get
        # a softened second attempt. Every failure is LOGGED, never swallowed.
        import time as _t
        for attempt, prompt in enumerate([shot["prompt"], shot["prompt"],
                                          "storyboard sketch, calm neutral mood: " + shot["prompt"]]):
            try:
                generate_still(prompt, size, out, ledger, refs=refs)
                break
            except Exception as e:
                if "Throttling" in str(getattr(getattr(e, "response", None), "text", "")):
                    _t.sleep(8)  # QPS-ліміт image-моделі: подихаємо і пробуємо ще
                detail = getattr(getattr(e, "response", None), "text", "") or str(e)
                print(f"[storyboard] shot {shot['id']:02} attempt {attempt + 1} failed: {detail[:200]}")
                if attempt == 2:
                    out = None  # text fallback on the board; never kills the run
        done += 1
        progress(done, len(shots))
        return out

    with ThreadPoolExecutor(max_workers=2) as pool:  # image QPS is tight
        return list(pool.map(one, shots))
