"""Concat clips + burn subtitles into the final film."""

import subprocess
from pathlib import Path

from . import config


def _srt_time(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},000"


def write_srt(shots: list[dict], path: Path):
    lines = []
    for i, shot in enumerate(shots):
        start, end = i * config.CLIP_SECONDS, (i + 1) * config.CLIP_SECONDS - 0.3
        lines += [str(i + 1), f"{_srt_time(start)} --> {_srt_time(end)}",
                  shot.get("subtitle", ""), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def assemble(clip_paths: list[Path], shots: list[dict], run_dir: Path) -> Path:
    concat_list = run_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))

    srt = run_dir / "subtitles.srt"
    write_srt(shots, srt)

    final = run_dir / "final.mp4"
    # cwd=run_dir so the subtitles filter finds its file; therefore every other
    # path must be relative to run_dir too (absolute-in-relative broke concat).
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", concat_list.name,
         "-vf", f"subtitles={srt.name}:force_style='FontSize=22,OutlineColour=&H80000000,BorderStyle=3'",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", final.name],
        check=True, cwd=run_dir)
    return final
