"""Concat clips + burn subtitles into the final film."""

import subprocess
from pathlib import Path

from . import config


def _srt_time(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02},000"


FADE = 0.4  # seconds of crossfade between shots — turns cuts into one film


def write_srt(shots: list[dict], path: Path):
    lines = []
    for i, shot in enumerate(shots):
        start = i * (config.CLIP_SECONDS - FADE)
        end = start + config.CLIP_SECONDS - FADE - 0.2
        lines += [str(i + 1), f"{_srt_time(start)} --> {_srt_time(end)}",
                  shot.get("subtitle", ""), ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def _size_of(clip: Path) -> str:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(clip)],
        check=True, capture_output=True, text=True).stdout.strip().splitlines()[0]
    return out  # "1080,1920"


def _normalize(clip_paths: list[Path]) -> list[Path]:
    """i2v clips are 1080p while t2v fallbacks are 720p; concat demands one size.
    Scale+pad every odd clip to the majority size."""
    sizes = [_size_of(p) for p in clip_paths]
    target = max(set(sizes), key=sizes.count)
    w, h = target.split(",")
    fixed = []
    for p, s in zip(clip_paths, sizes):
        if s == target:
            fixed.append(p)
            continue
        norm = p.with_name(p.stem + "_norm.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(p),
             "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(norm)],
            check=True)
        fixed.append(norm)
    return fixed


def _dur(clip: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(clip)],
        check=True, capture_output=True, text=True).stdout.strip()
    return float(out)


def assemble(clip_paths: list[Path], shots: list[dict], run_dir: Path) -> Path:
    clip_paths = _normalize(clip_paths)
    srt = run_dir / "subtitles.srt"
    write_srt(shots, srt)
    final = run_dir / "final.mp4"
    style = "FontSize=22,OutlineColour=&H80000000,BorderStyle=3"

    if len(clip_paths) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip_paths[0].resolve()),
             "-vf", f"subtitles={srt.name}:force_style='{style}'",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", final.name],
            check=True, cwd=run_dir)
        return final

    # crossfade chain: clips melt into each other instead of hard-cutting —
    # the difference between "N separate videos" and one film
    durs = [_dur(p) for p in clip_paths]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in clip_paths:
        cmd += ["-i", str(p.resolve())]
    chain = [f"[{i}:v]fps=24,settb=AVTB,format=yuv420p[p{i}]"
             for i in range(len(clip_paths))]
    prev, off = "[p0]", 0.0
    for i in range(1, len(clip_paths)):
        off += durs[i - 1] - FADE
        out = f"[x{i}]"
        chain.append(f"{prev}[p{i}]xfade=transition=fade:duration={FADE}:offset={off:.3f}{out}")
        prev = out
    chain.append(f"{prev}subtitles={srt.name}:force_style='{style}'[vout]")
    # cwd=run_dir so the subtitles filter finds its file (clip inputs are absolute)
    subprocess.run(cmd + ["-filter_complex", ";".join(chain), "-map", "[vout]",
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", final.name],
                   check=True, cwd=run_dir)
    return final
