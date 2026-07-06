"""Screenplay -> concrete shot list with text-to-video prompts."""

import json

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM = f"""You are a storyboard artist for a text-to-video model.
Turn the screenplay into exactly {config.TARGET_SHOTS} shots of {config.CLIP_SECONDS}s each.
Rules for prompts: begin every prompt with the screenplay's `style` sentence, then the
character's `visual` descriptor VERBATIM (this is what keeps the character consistent
across clips), then the shot content. One continuous simple action per shot. No text
overlays, no rapid cuts inside a shot.
Reply ONLY with JSON:
{{"shots": [{{"id": int, "scene_id": int, "prompt": str, "subtitle": str}}]}}"""


def plan_shots(screenplay: dict, ledger: Ledger) -> dict:
    return chat_json("shot_plan", config.MODEL_PLANNER, SYSTEM,
                     json.dumps(screenplay, ensure_ascii=False), ledger, thinking=False)
