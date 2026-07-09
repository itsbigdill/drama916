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
    fast = shots_target <= 6  # 15s/30s: skip deep thinking, one critic round
    def script_delta(text_so_far: str, kind: str):
        notify("script_live", json.dumps({"kind": kind, "tail": text_so_far[-700:]}))
    screenplay = write_screenplay(brief, ledger, on_delta=script_delta,
                                  thinking=not fast)
    # Style is not the writer's to invent — force the cast's fixed preset so the
    # look is predictable (warm 3D family-film) instead of a per-run lottery.
    screenplay["style"] = config.style_for_cast(cast)
    save("screenplay.json", screenplay)
    console.print(f"[bold]{screenplay['title']}[/] — {len(screenplay['scenes'])} scenes")
    notify("script", json.dumps({"title": screenplay.get("title", ""),
                                 "scenes": [{"id": sc.get("id"),
                                             "setting": str(sc.get("setting", ""))[:60],
                                             "action": str(sc.get("action", ""))[:160],
                                             "subtitle": str(sc.get("subtitle", ""))[:80]}
                                            for sc in screenplay.get("scenes", [])]}))

    # caption is part of the screenplay call now — zero extra latency
    caption = str(screenplay.get("caption") or
                  f"{screenplay.get('title', 'A short film')} 🎬 #shortfilm #ai").strip()
    (run_dir / "caption.txt").write_text(caption)

    console.rule("2/5 Shot plan")
    notify("board", "")
    shots = plan_shots(screenplay, ledger, target=shots_target)
    save("shots_draft.json", shots)
    notify("board", json.dumps({"shots": [{"id": s.get("id"),
                                           "subtitle": str(s.get("subtitle", ""))[:70],
                                           # show the ACTION, not the identical style prefix
                                           "prompt": (str(s.get("action", "")).strip()
                                                      or str(s.get("prompt", "")))[:110]}
                                          for s in shots.get("shots", [])]}))

    console.rule("3/5 Critic loop (text-only, cheap)")
    notify("critic", "")
    def critic_round(rnd: int, review: dict):
        fixes = [f.get("problem", "")[:60] for f in review.get("fixes", [])[:2]]
        notify("critic_live", json.dumps({"round": rnd, "score": review.get("score"),
                                          "fixes": fixes,
                                          "shots": len(review.get("revised_shots", []) or [])}))
    shots, critique_history = refine(shots, ledger, progress=critic_round,
                                     max_rounds=1 if fast else 2)
    save("shots_final.json", shots)
    save("critique_rounds.json", critique_history)
    n = len(shots["shots"])
    console.print(f"approved after {len(critique_history)} round(s), {n} shots")
    last_score = critique_history[-1].get("score") if critique_history else None

    def _clip(s, limit):  # word-boundary cut, no mid-word amputations in the UI
        s = str(s).strip()
        return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0] + "\u2026"

    notes = []
    for rev in critique_history:
        notes += [{"problem": _clip(f.get("problem", ""), 160),
                   "fix": _clip(f.get("fix", ""), 160)}
                  for f in rev.get("fixes", [])]
    rewrote = any(rev.get("revised_shots") for rev in critique_history)
    notify("critic", json.dumps({"rounds": len(critique_history), "score": last_score,
                                 "shots": n, "notes": notes[:6], "rewrote": rewrote,
                                 "verdict": _clip(critique_history[-1].get("verdict", ""), 220) if critique_history else ""}))

    estimate = n * config.COST_PER_CLIP_USD
    if not dry_run and estimate > config.MAX_BUDGET_USD:
        raise SystemExit(f"Estimated ${estimate:.2f} > MAX_BUDGET_USD "
                         f"${config.MAX_BUDGET_USD} — trim shots or raise the cap.")

    shot_list = shots["shots"]

    # Backend owns the character description (Series-Bible principle): the model
    # never writes appearance, so wardrobe/face can't drift shot to shot. Compose
    # each prompt from the LOCKED style + verbatim character visuals + the shot's
    # own action/emotion/camera/location.
    style = screenplay.get("style", "")
    char_visual = {c.get("name"): c.get("visual", "")
                   for c in screenplay.get("characters", [])}
    scene_setting = {sc.get("id"): sc.get("setting", "")
                     for sc in screenplay.get("scenes", [])}

    def compose_prompt(shot: dict) -> str:
        parts = [style] if style else []
        for name in (shot.get("characters") or []):
            v = char_visual.get(name)
            if v:
                parts.append(f"{name} — {v.strip().rstrip('.')}.")
        setting = scene_setting.get(shot.get("scene_id"))
        tail = ". ".join(x for x in [
            f"Location: {setting}" if setting else "",
            shot.get("action") or "", shot.get("emotion") or "",
            shot.get("camera") or ""] if x)
        if tail:
            parts.append(tail.rstrip(".") + ".")
        return " ".join(parts).strip()

    for s in shot_list:
        s["prompt"] = compose_prompt(s)
    save("shots_composed.json", shot_list)

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
            characters = screenplay.get("characters", [])[:4]
            portraits: dict = {}
            if characters:
                notify("stills", f"casting 0/{len(characters)}")
                portraits = cast_all(characters, size, run_dir / "cast", ledger,
                                     lambda d, n: notify("stills", f"casting {d}/{n}"),
                                     style=screenplay.get("style", ""))
            notify("stills", f"0/{len(shot_list)}")
            board_dir = run_dir / "board"
            def still_done(d, n, sid=None, path=""):
                if path == "rescue":
                    notify("stills", f"retrying shot {sid}")
                    return
                notify("stills", f"{d}/{n}")
                if path:
                    notify("still_live", json.dumps({"id": sid, "img": path}))
            paths = sketch_all(shot_list, size, board_dir, ledger, still_done,
                               portraits=portraits or None)
            stills = {s["id"]: str(p) for s, p in zip(shot_list, paths) if p}
        notify("approve", json.dumps({
            "estimate": 0 if dry_run else estimate,
            "size": size,
            "shots": [{"id": s["id"], "scene_id": s.get("scene_id"),
                       "subtitle": s.get("subtitle", ""),
                       "prompt": s.get("prompt", ""),
                       "img": stills.get(s["id"], "")} for s in shot_list]}))
        # blocks until the human approves; they may drop and/or reorder shots
        edits = approval() or {}
        dropped = set(edits.get("drop") or [])
        if dropped:
            shot_list = [s for s in shot_list if s["id"] not in dropped]
            stills = {k: v for k, v in stills.items() if k not in dropped}
            estimate = len(shot_list) * config.COST_PER_CLIP_USD
            console.print(f"human dropped shots {sorted(dropped)} -> {len(shot_list)} remain")
        order = edits.get("order") or []
        if order:  # human reordered the storyboard — film & voice in that sequence
            pos = {sid: i for i, sid in enumerate(order)}
            shot_list.sort(key=lambda s: pos.get(s["id"], 1e9))
            console.print(f"human reordered shots -> {[s['id'] for s in shot_list]}")

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

    # Dailies QC is optional (config.DAILIES_QC) — off by default for speed.
    if dry_run or not config.DAILIES_QC:
        pass
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
            notify("dailies_live", json.dumps({"id": shot["id"], "ok": verdict["ok"],
                                               "reason": verdict["reason"][:80]}))
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

    # Voice the dialogue — each line spoken by its character, voice by gender.
    audio: dict[int, Path] = {}
    if not dry_run:
        from .tts import voice_all
        char_gender = {c.get("name"): (c.get("gender") or "neutral").lower()
                       for c in screenplay.get("characters", [])}
        scene_speaker = {sc.get("id"): sc.get("speaker")
                         for sc in screenplay.get("scenes", [])}

        def voice_for(shot: dict) -> str:
            # the shot's own speaker wins (a scene can hold two speakers across
            # its shots); fall back to the scene's speaker only if untagged
            speaker = shot.get("speaker") or scene_speaker.get(shot.get("scene_id"))
            gender = char_gender.get(speaker, "neutral")
            return config.VOICE_BY_GENDER.get(gender, config.TTS_VOICE)

        n_lines = sum(1 for s in shot_list if str(s.get("subtitle", "")).strip())
        if n_lines:
            notify("voice", f"0/{n_lines}")
            audio = voice_all(shot_list, run_dir / "audio", ledger,
                              lambda d, n: notify("voice", f"{d}/{n}"),
                              voice_for=voice_for)

    console.rule("5/5 Assemble")
    notify("cut", "")
    final = assemble(clip_paths, shot_list, run_dir, audio=audio)

    ledger.save(str(run_dir / "run_report.json"))
    ledger.print_table()
    console.print(f"\n[bold green]Done:[/] {final}")
    notify("done", json.dumps({"cost": ledger.total_usd, "video": str(final),
                               "caption": caption}))
    return final
