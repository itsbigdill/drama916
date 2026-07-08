"""Voice-over — the dialogue lines become spoken audio (qwen3-tts-flash).

The film is no longer silent-with-subtitles: each shot's line is synthesized
and, in assembly, mixed onto the video at that shot's time window. No burned-in
text — the story is carried by voice.
"""

import os
from pathlib import Path
from typing import Callable

import httpx

from . import config
from .ledger import Ledger

URL = f"{config.DASHSCOPE_API_BASE}/api/v1/services/aigc/multimodal-generation/generation"


def synthesize(text: str, out_path: Path, ledger: Ledger,
               voice: str | None = None) -> Path | None:
    """One line -> a wav file. Returns None on any failure (voice is optional;
    a missing line must never sink an already-shot film)."""
    text = (text or "").strip()
    if not text:
        return None
    r = httpx.post(
        URL,
        headers={"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
                 "Content-Type": "application/json"},
        json={"model": config.MODEL_TTS,
              "input": {"text": text, "voice": voice or config.TTS_VOICE,
                        "language_type": "English"}},
        timeout=60)
    r.raise_for_status()
    url = r.json().get("output", {}).get("audio", {}).get("url")
    if not url:
        return None
    audio = httpx.get(url, timeout=60)
    audio.raise_for_status()
    out_path.write_bytes(audio.content)
    ledger.record("voice", config.MODEL_TTS, clips=1,
                  clip_cost=config.COST_PER_TTS_LINE_USD)
    return out_path


def voice_all(shots: list[dict], audio_dir: Path, ledger: Ledger,
              progress: Callable[[int, int], None] | None = None,
              voice: str | None = None) -> dict[int, Path]:
    """Synthesize every shot that has a line. Serial (TTS is fast, ~2s/line)
    and failure-tolerant: a line that fails is simply left silent."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    out: dict[int, Path] = {}
    lines = [s for s in shots if str(s.get("subtitle", "")).strip()]
    for i, shot in enumerate(lines, 1):
        wav = audio_dir / f"shot_{shot['id']:02}.wav"
        try:
            if synthesize(shot["subtitle"], wav, ledger, voice=voice):
                out[shot["id"]] = wav
        except Exception as e:
            detail = getattr(getattr(e, "response", None), "text", "") or str(e)
            print(f"[tts] shot {shot['id']:02} failed: {detail[:160]}")
        if progress:
            progress(i, len(lines))
    return out
