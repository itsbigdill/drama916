"""Central config. Model ids verified against Model Studio intl docs on 2026-07-04.

If a model id 404s, check the current list:
https://www.alibabacloud.com/help/en/model-studio/getting-started/models
"""

BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_API_BASE = "https://dashscope-intl.aliyuncs.com"  # native API (video tasks)

# Text models
MODEL_WRITER = "qwen3.7-max"      # screenplay quality matters most
MODEL_PLANNER = "qwen3.7-plus"    # shot planning / critic — cheaper, plenty good
MODEL_CHEAP = "qwen3.6-flash"     # smoke tests, summaries

# Video / image
MODEL_VIDEO = "happyhorse-1.1-t2v"
MODEL_VIDEO_I2V = "happyhorse-1.1-i2v"   # approved still becomes the first frame
MODEL_IMAGE = "qwen-image-2.0-pro"
# Voice — the dialogue lines are spoken instead of shown as burned-in subtitles
MODEL_TTS = "qwen3-tts-flash"
TTS_VOICE = "Cherry"              # fallback
VOICE_BY_GENDER = {"female": "Cherry", "male": "Ethan", "neutral": "Nofish"}
COST_PER_TTS_LINE_USD = 0.002    # rough; qwen3-tts-flash is per-character and cheap
# Calibrated against real coupon redemptions (July 15, 2026, 6-shot film):
# images billed ~$0.60 for a cast+stills pass (~8 images) -> ~$0.075 each.
COST_PER_STILL_USD = 0.075
IMAGE_MIN_GAP_SEC = 12            # min seconds between qwen-image calls (QPM guard)
# happyhorse-1.1 i2v REAL billing: $0.54 per 5s 1080p clip = $0.108/s (list
# price said ~$0.165 — the console promo is real). 720p unverified: scaled by
# the same promo ratio from its $0.125 list estimate.
VIDEO_RATE_PER_SEC = {"720": 0.082, "1080": 0.108}
VIDEO_SIZE = "1280*720"
CLIP_SECONDS = 5

# Budget rails — calibrated July 15 against real coupon redemptions.
COST_PER_CLIP_USD = 0.54          # 5s @ 1080p i2v, actual billed rate
MAX_BUDGET_USD = 20.00            # hard stop for a single run
MAX_CRITIC_ROUNDS = 3
TARGET_SHOTS = 12                 # ~60s film at 5s/clip
CONCURRENT_CLIPS = 4              # HappyHorse ~3min/clip; parallel keeps wall-clock sane
MAX_RESHOOTS = 3                  # dailies QC may reshoot at most this many takes per film
DAILIES_QC = False                # optional post-shoot VL review; off = faster pipeline

import os
# where finished runs are written. On read-only hosts (FC code dir is read-only,
# only /tmp is writable) set RUNS_DIR=/tmp/runs; defaults to ./runs locally.
RUNS_DIR = os.environ.get("RUNS_DIR", "runs")

# Visual style is NOT left to the writer's imagination anymore — it is a fixed
# preset chosen by the selected cast. Keyed by the cast option value ("" = Auto).
# This prepends to every shot prompt (shot_planner rule), so the whole film keeps
# one predictable look instead of a per-run lottery (photoreal macro vs stop-motion).
_STYLE_AUTO = ("Warm cinematic 3D animated family-film style, with expressive "
               "character-aware designs, soft rounded shapes, big emotional eyes, "
               "and cozy storytelling. Soft golden lighting, detailed textures "
               "adapted to the character type, pastel colors, shallow depth of field, "
               "polished high-quality render, wholesome whimsical mood.")
STYLE_BY_CAST = {
    "": _STYLE_AUTO,
    "realistic human characters": (
        "Warm cinematic 3D animated family-film style, with expressive stylized "
        "human characters, soft rounded features, natural proportions, and cozy "
        "emotional storytelling. Soft golden lighting, realistic skin and clothing "
        "details, pastel colors, shallow depth of field, polished high-quality "
        "render, wholesome heartfelt mood."),
    "anthropomorphic fruit and vegetable characters": (
        "Warm cinematic 3D animated family-film style, with expressive anthropomorphic "
        "fruit characters, soft rounded shapes, big emotional eyes, and cozy playful "
        "storytelling. Soft golden lighting, detailed natural fruit textures, pastel "
        "colors, shallow depth of field, polished high-quality render, wholesome "
        "whimsical mood."),
    "animal characters": (
        "Warm cinematic 3D animated family-film style, with expressive anthropomorphic "
        "animal characters, soft friendly proportions, big emotional eyes, and cozy "
        "adventure storytelling. Soft golden lighting, detailed fur, feathers, or skin "
        "textures, pastel colors, shallow depth of field, polished high-quality render, "
        "wholesome charming mood."),
    "everyday objects brought to life as characters": (
        "Warm cinematic 3D animated family-film style, with expressive anthropomorphic "
        "everyday object characters, soft rounded shapes, subtle faces, and cozy magical "
        "storytelling. Soft golden lighting, detailed material textures, pastel colors, "
        "shallow depth of field, polished high-quality render, wholesome whimsical mood."),
}


def style_for_cast(cast: str) -> str:
    return STYLE_BY_CAST.get(cast or "", _STYLE_AUTO)
