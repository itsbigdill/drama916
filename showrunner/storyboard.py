"""Visual storyboard — a still frame per shot, drawn before any video is filmed.

The human approves PICTURES, not prompts. Stills are cheap (~12s, cents) and
they double as the visual anchor for image-to-video continuity later.
"""

import base64
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

import httpx

from . import config
from .ledger import Ledger

URL = f"{config.DASHSCOPE_API_BASE}/api/v1/services/aigc/multimodal-generation/generation"

# qwen-image has a tight per-minute quota on fresh accounts. A global minimum
# gap between ANY two image calls (portraits + stills + rescues) keeps us under
# it, so generations succeed instead of failing and falling back to duplicate
# portrait stand-ins. Trades a little speed for real, distinct frames.
_img_lock = threading.Lock()
_img_last = [0.0]


def _throttle() -> None:
    with _img_lock:
        wait = config.IMAGE_MIN_GAP_SEC - (time.time() - _img_last[0])
        if wait > 0:
            time.sleep(wait)
        _img_last[0] = time.time()


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _generate(content: list[dict], size: str, out_path: Path, ledger: Ledger,
              stage: str) -> Path:
    _throttle()
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


def generate_portrait(character: dict, size: str, out_path: Path, ledger: Ledger,
                      style: str = "") -> Path:
    """One canonical reference portrait per character (the 'character sheet').
    The style preset MUST lead here too — the portrait is the reference every
    shot is locked to, so if it renders photoreal the whole film goes photoreal
    no matter what the shot prompts say."""
    lead = (style.strip() + " ") if style else ""
    content = [{"text": f"{lead}Character reference sheet, single character, full body, "
                        "front view, neutral studio background, even lighting: "
                        f"{character.get('name', '')} — {character.get('visual', '')}"}]
    return _generate(content, size, out_path, ledger, "cast_sheet")


def cast_all(characters: list[dict], size: str, cast_dir: Path, ledger: Ledger,
             progress: Callable[[int, int], None], style: str = "") -> dict[str, Path]:
    """Portrait per character -> {name: path}, in the film's style. Retries on
    throttle so a character never silently vanishes for lack of a reference."""
    cast_dir.mkdir(parents=True, exist_ok=True)
    done = 0

    def one(ch: dict) -> tuple[str, Path | None]:
        nonlocal done
        name = ch.get("name", "x")
        safe = "".join(c for c in name if c.isalnum()) or "x"
        out: Path | None = cast_dir / f"{safe}.png"
        for attempt in range(3):
            try:
                generate_portrait(ch, size, out, ledger, style=style)
                break
            except Exception as e:
                detail = getattr(getattr(e, "response", None), "text", "") or str(e)
                print(f"[cast] portrait '{name}' attempt {attempt+1} failed: {detail[:160]}")
                if "Throttling" in detail and attempt < 2:
                    time.sleep(15)
                    continue
                out = None
                break
        done += 1
        progress(done, len(characters))
        return name, out

    with ThreadPoolExecutor(max_workers=2) as pool:  # image QPS is tight
        return {name: p for name, p in pool.map(one, characters) if p}


def _try_still(prompt: str, size: str, out: Path, ledger: Ledger,
               refs: list[Path] | None, tag: str) -> str | None:
    """None on success; a short failure reason otherwise."""
    try:
        generate_still(prompt, size, out, ledger, refs=refs)
        return None
    except Exception as e:
        detail = getattr(getattr(e, "response", None), "text", "") or str(e)
        print(f"[storyboard] {tag} failed: {detail[:180]}")
        if "Throttling" in detail or "429" in detail:
            time.sleep(15)  # квота хвилинна — коротка пауза її не рятує
            return "rate limit"
        if "DataInspection" in detail:
            return "moderation"
        return "generation failed"


def _sanitized(prompt: str, ledger: Ledger) -> str:
    """Moderation-safe rewrite of a shot prompt (cheap flash call)."""
    from .llm import chat
    try:
        return chat("still_sanitize", config.MODEL_CHEAP,
                    "Rewrite the image prompt so it passes strict content moderation. "
                    "Keep the scene, characters and mood. Remove anything violent, dark "
                    "or brand/person-specific, AND rewrite any physically intimate or "
                    "suggestive wording (kiss, embrace, bodies pressed, intimacy, "
                    "passionate, seductive) into innocent G-rated symbolic staging: "
                    "standing close, leaning heads together, holding hands, hearts or "
                    "sparkles floating. Reply with the rewritten prompt only.",
                    prompt, ledger, thinking=False).strip()
    except Exception:
        return "gentle storyboard sketch: " + prompt


def sketch_all(shots: list[dict], size: str, board_dir: Path, ledger: Ledger,
               progress: Callable[[int, int], None],
               portraits: dict[str, Path] | None = None
               ) -> tuple[list[Path | None], dict[int, str]]:
    """Draw each shot against ONLY the portraits of the characters actually in it.
    Ladder per shot: retry → softened → flash-sanitized rescue sweeps. NO
    fallbacks: a frame that can't be generated stays empty and its failure
    reason (moderation / rate limit) is returned so the UI shows it honestly —
    the human fixes it with a redraw note or removes the shot."""
    board_dir.mkdir(parents=True, exist_ok=True)
    portraits = portraits or {}
    done = 0
    results: dict[int, Path | None] = {}
    reasons: dict[int, str] = {}

    def refs_for(shot: dict) -> list[Path] | None:
        names = shot.get("characters")
        if names is None:  # planner didn't tag → fall back to the whole cast
            return list(portraits.values()) or None
        r = [portraits[n] for n in names if n in portraits]
        return r or None  # tagged but no portrait → rely on the text, don't force wrong ones

    def one(shot: dict) -> None:
        nonlocal done
        refs = refs_for(shot)
        out = board_dir / f"shot_{shot['id']:02}.png"
        err = _try_still(shot["prompt"], size, out, ledger, refs, f"shot {shot['id']:02} a1")
        if err:
            err = _try_still(shot["prompt"], size, out, ledger, refs, f"shot {shot['id']:02} a2")
        if err:
            err = _try_still("storyboard sketch, calm neutral mood: " + shot["prompt"],
                             size, out, ledger, refs, f"shot {shot['id']:02} a3")
        results[shot["id"]] = None if err else out
        if err:
            reasons[shot["id"]] = err
        done += 1
        progress(done, len(shots), shot["id"], "" if err else str(out))

    # _throttle() already paces every call, so parallelism just fills the gaps
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, shots))

    # serial rescue sweeps: sanitized prompt (strips moderation-triggering
    # wording), generous spacing for the per-minute quota. Still the REAL frame —
    # same scene, same characters — not a substitute.
    for round_no in (1, 2):
        for shot in shots:
            if results[shot["id"]] is not None:
                continue
            progress(done, len(shots), shot["id"], "rescue")
            time.sleep(20)
            out = board_dir / f"shot_{shot['id']:02}.png"
            clean = _sanitized(shot["prompt"], ledger)
            err = _try_still(clean, size, out, ledger, refs_for(shot),
                             f"shot {shot['id']:02} rescue r{round_no}")
            if not err:
                results[shot["id"]] = out
                reasons.pop(shot["id"], None)
                progress(done, len(shots), shot["id"], str(out))
            else:
                reasons[shot["id"]] = err

    return [results[s["id"]] for s in shots], reasons
