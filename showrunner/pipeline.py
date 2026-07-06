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


def run(logline: str, dry_run: bool = False, cb: ProgressCB = None) -> Path:
    notify = cb or (lambda stage, detail: None)
    ledger = Ledger()
    run_dir = Path(config.RUNS_DIR) / time.strftime("%m%d-%H%M%S")
    clips_dir = run_dir / "clips"
    clips_dir.mkdir(parents=True)

    def save(name: str, obj):
        (run_dir / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False))

    console.rule("1/5 Screenplay")
    notify("script", "")
    screenplay = write_screenplay(logline, ledger)
    save("screenplay.json", screenplay)
    console.print(f"[bold]{screenplay['title']}[/] — {len(screenplay['scenes'])} scenes")
    notify("script", screenplay.get("title", ""))

    console.rule("2/5 Shot plan")
    notify("board", "")
    shots = plan_shots(screenplay, ledger)
    save("shots_draft.json", shots)

    console.rule("3/5 Critic loop (text-only, cheap)")
    notify("critic", "")
    shots, critique_history = refine(shots, ledger)
    save("shots_final.json", shots)
    save("critique_rounds.json", critique_history)
    n = len(shots["shots"])
    console.print(f"approved after {len(critique_history)} round(s), {n} shots")
    notify("critic", f"{len(critique_history)} rounds")

    estimate = n * config.COST_PER_CLIP_USD
    if not dry_run and estimate > config.MAX_BUDGET_USD:
        raise SystemExit(f"Estimated ${estimate:.2f} > MAX_BUDGET_USD "
                         f"${config.MAX_BUDGET_USD} — trim shots or raise the cap.")

    # HappyHorse takes ~3 min per clip; sequential = ~40 min per film.
    # Generate concurrently (tasks queue server-side) — wall clock ≈ one clip.
    console.rule(f"4/5 Video generation ({'DRY RUN' if dry_run else f'~${estimate:.0f}'})")
    shot_list = shots["shots"]
    done_count = 0

    def make(shot: dict) -> Path:
        nonlocal done_count
        out = clips_dir / f"shot_{shot['id']:02}.mp4"
        console.print(f"  shot {shot['id']}: {shot['prompt'][:70]}…")
        path = generate_clip(shot, out, ledger, dry_run)
        done_count += 1
        notify("film", f"{done_count}/{len(shot_list)}")
        return path

    notify("film", f"0/{len(shot_list)}")
    with ThreadPoolExecutor(max_workers=config.CONCURRENT_CLIPS) as pool:
        clip_paths = list(pool.map(make, shot_list))

    console.rule("5/5 Assemble")
    notify("cut", "")
    final = assemble(clip_paths, shot_list, run_dir)

    ledger.save(str(run_dir / "run_report.json"))
    ledger.print_table()
    console.print(f"\n[bold green]Done:[/] {final}")
    notify("done", f"{ledger.total_usd}|{final}")
    return final
