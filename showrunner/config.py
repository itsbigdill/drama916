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
COST_PER_STILL_USD = 0.04         # qwen-image-2.0-pro, ще не підтверджено консоллю
# happyhorse-1.1 intl list price per OUTPUT second (July 2026): ~0.9 RMB/s 720p,
# ~1.2 RMB/s 1080p -> USD; promo in console may be ~40% lower
VIDEO_RATE_PER_SEC = {"720": 0.125, "1080": 0.165}
VIDEO_SIZE = "1280*720"
CLIP_SECONDS = 5

# Budget rails — UPDATE COST_PER_CLIP after the first real generation on July 5,
# the console shows the actual charge per task.
COST_PER_CLIP_USD = 0.85          # 5s @ 1080p list (i2v upscales to 1080)
MAX_BUDGET_USD = 20.00            # hard stop for a single run
MAX_CRITIC_ROUNDS = 3
TARGET_SHOTS = 12                 # ~60s film at 5s/clip
CONCURRENT_CLIPS = 4              # HappyHorse ~3min/clip; parallel keeps wall-clock sane
MAX_RESHOOTS = 3                  # dailies QC may reshoot at most this many takes per film
DAILIES_QC = False                # optional post-shoot VL review; off = faster pipeline

RUNS_DIR = "runs"
