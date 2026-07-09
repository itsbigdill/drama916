"""Screenplay -> concrete shot list with text-to-video prompts."""

import json

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM_TMPL = """You are a storyboard artist for a text-to-video model.
Turn the screenplay into exactly {target} shots of {secs}s each.
Rules for prompts: begin every prompt with the screenplay's `style` sentence, then copy
each PRESENT character's `visual` descriptor WORD-FOR-WORD (do NOT paraphrase or change
their outfit/features — this is what keeps them consistent across clips), then the shot
content. One continuous simple action per shot. No text overlays, no rapid cuts.
For EACH shot also fill:
- `characters`: NAMES of the characters visible in that shot (subset of the cast);
- `speaker`: NAME of the character who says that shot's line, "" if the shot is silent;
- `action`: one short plain-language line of what happens (NO style or camera words).
Reply ONLY with JSON:
{{"shots": [{{"id": int, "scene_id": int, "prompt": str, "subtitle": str,
   "speaker": str, "characters": [str], "action": str}}]}}"""


def plan_shots(screenplay: dict, ledger: Ledger,
               target: int = config.TARGET_SHOTS) -> dict:
    system = SYSTEM_TMPL.format(target=target, secs=config.CLIP_SECONDS)
    return chat_json("shot_plan", config.MODEL_PLANNER, system,
                     json.dumps(screenplay, ensure_ascii=False), ledger, thinking=False)
