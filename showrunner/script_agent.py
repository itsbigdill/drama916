"""Logline -> screenplay JSON."""

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM = """You are an award-winning short-form screenwriter. Given a logline you
write a complete screenplay for a ~60 second silent-with-subtitles short drama.
Constraints: 3-act arc, at most 4 scenes, one or two characters, strong visual
storytelling (a video model will render it — no complex physics, no text in frame,
no fast camera moves). Reply ONLY with JSON:
{"title": str, "logline": str, "style": str,  # one reusable visual style sentence
 "characters": [{"name": str, "visual": str}],  # stable visual descriptor, reused verbatim in every shot
 "scenes": [{"id": int, "setting": str, "action": str, "subtitle": str, "mood": str}]}"""


def write_screenplay(logline: str, ledger: Ledger, on_delta=None) -> dict:
    return chat_json("screenplay", config.MODEL_WRITER, SYSTEM,
                     f"Logline: {logline}", ledger, on_delta=on_delta)
