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

# Video
MODEL_VIDEO = "happyhorse-1.1-t2v"
VIDEO_SIZE = "1280*720"
CLIP_SECONDS = 5

# Budget rails — UPDATE COST_PER_CLIP after the first real generation on July 5,
# the console shows the actual charge per task.
COST_PER_CLIP_USD = 1.00          # pessimistic placeholder
MAX_BUDGET_USD = 20.00            # hard stop for a single run
MAX_CRITIC_ROUNDS = 3
TARGET_SHOTS = 12                 # ~60s film at 5s/clip
CONCURRENT_CLIPS = 4              # HappyHorse ~3min/clip; parallel keeps wall-clock sane

RUNS_DIR = "runs"
