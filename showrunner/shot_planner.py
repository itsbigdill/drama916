"""Screenplay -> concrete shot list with text-to-video prompts."""

import json

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM_TMPL = """You are a storyboard artist for a text-to-video model.
Turn the screenplay into exactly {target} shots of {secs}s each.
Do NOT describe how the characters LOOK (their appearance, face, outfit, colors are
locked elsewhere and injected automatically). Only describe what happens.
One continuous simple action per shot. No text overlays, no rapid cuts.
MODERATION RULE: actions and emotions go straight into an image model with a strict
content filter. Describe physical closeness symbolically and G-rated — standing close,
leaning heads together, holding hands, hearts or sparkles floating. NEVER use words
like kiss, embrace, intimacy, passionate, seductive, bodies pressed together.
For EACH shot fill:
- `characters`: NAMES of every character visible OR physically present in that shot,
  even partially — if the action mentions any part of a character (their hands,
  shoulder, lap, silhouette), tag that character too, otherwise the image model
  will invent generic human body parts;
- `speaker`: NAME of the character who says that shot's line, "" if the shot is silent;
- `action`: one short plain-language line of the physical action/staging;
- `emotion`: the mood/feeling of the shot in a few words;
- `camera`: framing/shot type (e.g. "tight vertical close-up", "wide two-shot").
Reply ONLY with JSON:
{{"shots": [{{"id": int, "scene_id": int, "subtitle": str, "speaker": str,
   "characters": [str], "action": str, "emotion": str, "camera": str}}]}}"""


def plan_shots(screenplay: dict, ledger: Ledger,
               target: int = config.TARGET_SHOTS) -> dict:
    system = SYSTEM_TMPL.format(target=target, secs=config.CLIP_SECONDS)
    return chat_json("shot_plan", config.MODEL_PLANNER, system,
                     json.dumps(screenplay, ensure_ascii=False), ledger, thinking=False)
