"""Orchestrator: logline in, final.mp4 + run_report.json out."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from rich.console import Console

from . import config
from .assemble import assemble
from .critic import refine
from .ledger import Ledger
from .script_agent import write_screenplay
from .shot_planner import plan_shots
from .video_gen import generate_clip

console = Console()

# progress callback: cb(stage, detail) — stages: script, board, critic, film, cut, done
ProgressCB = Optional[Callable[[str, str], None]]


def run(logline: str, dry_run: bool = False, cb: ProgressCB = None,
        vertical: bool = False, approval: Optional[Callable[[], None]] = None,
        shots_target: int = config.TARGET_SHOTS, genre: str = "",
        cast: str = "") -> Path:
    """approval: optional blocking human checkpoint called AFTER the critic and
    BEFORE any video credit is spent. The web UI shows the storyboard and blocks
    here until the human hits Film it. CLI passes None (no pause)."""
    notify = cb or (lambda stage, detail: None)
    size = "720*1280" if vertical else config.VIDEO_SIZE
    ledger = Ledger()
    run_dir = Path(config.RUNS_DIR) / time.strftime("%m%d-%H%M%S")
    clips_dir = run_dir / "clips"
    clips_dir.mkdir(parents=True)

    def save(name: str, obj):
        (run_dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False))

    console.rule("1/5 Screenplay")
    notify("script", "")
    brief = logline
    if genre:
        brief += f"\nGenre: {genre}."
    if cast:
        brief += f"\nCasting rule: ALL characters are {cast}; write their visual descriptors accordingly."
    screenplay = write_screenplay(brief, ledger)
    save("screenplay.json", screenplay)
    console.print(f"[bold]{screenplay['title']}[/] — {len(screenplay['scenes'])} scenes")
    notify("script", json.dumps({"title": screenplay.get("title", ""),
                                 "scenes": len(screenplay.get("scenes", []))}))

    # a TikTok-ready caption, written while the board is being planned (cheap, flash)
    from .llm import chat
    caption = chat("caption", config.MODEL_CHEAP,
                   "You write TikTok captions. Reply with ONLY the caption text: "
                   "one hook line under 100 chars, then 4 relevant hashtags.",
                   f"Short film: {screenplay.get('title')} — {screenplay.get('logline', logline)}",
                   ledger, thinking=False).strip()
    (run_dir / "caption.txt").write_text(caption)

    console.rule("2/5 Shot plan")
    notify("board", "")
    shots = plan_shots(screenplay, ledger, target=shots_target)
    save("shots_draft.json", shots)
    notify("board", json.dumps({"shots": len(shots.get("shots", []))}))

    console.rule("3/5 Critic loop (text-only, cheap)")
    notify("critic", "")
    shots, critique_history = refine(shots, ledger)
    save("shots_final.json", shots)
    save("critique_rounds.json", critique_history)
    n = len(shots["shots"])
    console.print(f"approved after {len(critique_history)} round(s), {n} shots")
    last_score = critique_history[-1].get("score") if critique_history else None
    notify("critic", json.dumps({"rounds": len(critique_history), "score": last_score,
                                 "shots": n}))

    estimate = n * config.COST_PER_CLIP_USD
    if not dry_run and estimate > config.MAX_BUDGET_USD:
        raise SystemExit(f"Estimated ${estimate:.2f} > MAX_BUDGET_USD "
                         f"${config.MAX_BUDGET_USD} — trim shots or raise the cap.")

    shot_list = shots["shots"]
    if vertical:  # framing hint must be in place BEFORE stills, so board == film
        for s in shot_list:
            s["prompt"] = "Vertical 9:16 composition, subject centered. " + s["prompt"]

    stills: dict[int, str] = {}
    if approval is not None:
        # draw the storyboard as pictures — the human approves frames, not prompts
        if not dry_run:
            from .storyboard import cast_all, sketch_all
            # character sheets first: one canonical portrait per character, then
            # every still is generated AGAINST those portraits → same faces across
            # the whole board (and, via i2v, across the whole film)
            characters = screenplay.get("characters", [])[:3]
            refs: list = []
            if characters:
                notify("stills", f"casting 0/{len(characters)}")
                refs = cast_all(characters, size, run_dir / "cast", ledger,
                                lambda d, n: notify("stills", f"casting {d}/{n}"))
            notify("stills", f"0/{len(shot_list)}")
            board_dir = run_dir / "board"
            paths = sketch_all(shot_list, size, board_dir, ledger,
                               lambda d, n: notify("stills", f"{d}/{n}"),
                               refs=refs or None)
            stills = {s["id"]: str(p) for s, p in zip(shot_list, paths) if p}
        notify("approve", json.dumps({
            "estimate": 0 if dry_run else estimate,
            "shots": [{"id": s["id"], "subtitle": s.get("subtitle", ""),
                       "prompt": s.get("prompt", ""),
                       "img": stills.get(s["id"], "")} for s in shot_list]}))
        approval()  # blocks until the human approves the storyboard

    # HappyHorse takes ~3 min per clip; sequential = ~40 min per film.
    # Generate concurrently (tasks queue server-side) — wall clock ≈ one clip.
    console.rule(f"4/5 Video generation ({'DRY RUN' if dry_run else f'~${estimate:.0f}'})")
    done_count = 0

    def first_frame_of(shot: dict) -> Path | None:
        p = stills.get(shot["id"])
        return Path(p) if p else None

    def make(shot: dict) -> Path:
        nonlocal done_count
        out = clips_dir / f"shot_{shot['id']:02}.mp4"
        console.print(f"  shot {shot['id']}: {shot['prompt'][:70]}…")
        path = generate_clip(shot, out, ledger, dry_run, size=size,
                             first_frame=first_frame_of(shot))
        done_count += 1
        notify("film", f"{done_count}/{len(shot_list)}")
        return path

    notify("film", f"0/{len(shot_list)}")
    with ThreadPoolExecutor(max_workers=config.CONCURRENT_CLIPS) as pool:
        clip_paths = list(pool.map(make, shot_list))

    # Dailies: the agent screens every take and reshoots the broken ones.
    # Skipped on dry runs (placeholder cards have nothing to review).
    if dry_run:
        notify("dailies", json.dumps({"approved": len(shot_list), "reshot": 0}))
    else:
        from .dailies import review_take
        console.rule("Dailies review")
        notify("dailies", "")
        reshoots_left = config.MAX_RESHOOTS
        reshot, reports = 0, []
        for i, (shot, clip) in enumerate(zip(shot_list, clip_paths), 1):
            notify("dailies", f"{i}/{len(shot_list)}")
            # QC is advisory: any failure here must never sink an already-shot film
            try:
                verdict = review_take(clip, shot, ledger)
            except Exception as e:
                console.print(f"  shot {shot['id']}: review failed ({e}) — keeping the take")
                continue
            if verdict["ok"] or reshoots_left == 0:
                if not verdict["ok"]:
                    console.print(f"  shot {shot['id']} flagged but reshoot budget spent")
                continue
            console.print(f"  ✗ shot {shot['id']}: {verdict['reason']} — reshooting")
            reports.append({"shot": shot["id"], "reason": verdict["reason"]})
            reshoots_left -= 1
            reshot += 1
            try:
                generate_clip(shot, clip, ledger, dry_run, size=size,
                              first_frame=first_frame_of(shot))  # overwrite the take
            except Exception as e:
                console.print(f"  reshoot of shot {shot['id']} failed ({e}) — keeping original")
        save("dailies.json", reports)
        notify("dailies", json.dumps({"approved": len(shot_list) - reshot,
                                      "reshot": reshot,
                                      "last_reason": reports[-1]["reason"] if reports else ""}))

    console.rule("5/5 Assemble")
    notify("cut", "")
    final = assemble(clip_paths, shot_list, run_dir)

    ledger.save(str(run_dir / "run_report.json"))
    ledger.print_table()
    console.print(f"\n[bold green]Done:[/] {final}")
    notify("done", json.dumps({"cost": ledger.total_usd, "video": str(final),
                               "caption": caption}))
    return final
