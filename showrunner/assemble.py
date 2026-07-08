"""Concat clips into one film, crossfaded, with spoken dialogue mixed in.

No burned-in subtitles — each shot's line is voiced (see tts.py) and mixed
onto the video at that shot's time window.
"""

import subprocess
from pathlib import Path

from . import config

FADE = 0.4  # seconds of crossfade between shots — turns cuts into one film


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


def assemble(clip_paths: list[Path], shots: list[dict], run_dir: Path,
             audio: dict[int, Path] | None = None) -> Path:
    """audio: shot_id -> wav of that shot's spoken line (optional)."""
    audio = audio or {}
    clip_paths = _normalize(clip_paths)
    durs = [_dur(p) for p in clip_paths]
    # each shot's start on the crossfaded timeline (mirror the xfade offsets)
    offsets = [0.0]
    for i in range(1, len(clip_paths)):
        offsets.append(offsets[-1] + durs[i - 1] - FADE)

    final = run_dir / "final.mp4"
    has_audio = any(s.get("id") in audio for s in shots)
    video_out = (run_dir / "silent.mp4") if has_audio else final

    # 1) the (subtitle-free) video
    if len(clip_paths) == 1:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip_paths[0].resolve()),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", video_out.name],
            check=True, cwd=run_dir)
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for p in clip_paths:
            cmd += ["-i", str(p.resolve())]
        chain = [f"[{i}:v]fps=24,settb=AVTB,format=yuv420p[p{i}]"
                 for i in range(len(clip_paths))]
        prev = "[p0]"
        for i in range(1, len(clip_paths)):
            out = f"[x{i}]"
            chain.append(f"{prev}[p{i}]xfade=transition=fade:"
                         f"duration={FADE}:offset={offsets[i]:.3f}{out}")
            prev = out
        subprocess.run(cmd + ["-filter_complex", ";".join(chain), "-map", prev,
                              "-c:v", "libx264", "-pix_fmt", "yuv420p", video_out.name],
                       check=True, cwd=run_dir)

    if not has_audio:
        return final

    # 2) mix each line onto the timeline at its shot's offset, then mux
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video_out.name]
    voiced = [(idx, s) for idx, s in enumerate(shots) if s.get("id") in audio]
    for _, s in voiced:
        cmd += ["-i", str(audio[s["id"]].resolve())]
    fc, labels = [], []
    for j, (idx, s) in enumerate(voiced, start=1):
        ms = int(offsets[idx] * 1000)
        fc.append(f"[{j}:a]adelay={ms}|{ms}[a{j}]")
        labels.append(f"[a{j}]")
    fc.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0[aout]")
    subprocess.run(cmd + ["-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[aout]",
                          "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", final.name],
                   check=True, cwd=run_dir)
    return final
