"""Logline -> screenplay JSON."""

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM = """You are an award-winning short-form screenwriter. Given a logline you
write a complete screenplay for a ~60 second silent-with-subtitles short drama.
Keep EVERY character the logline names — never drop one to simplify the story. Reply ONLY with JSON:
{"title": str, "logline": str, "style": str,  # one reusable visual style sentence
 "caption": str,  # TikTok caption: one hook line under 100 chars, then 4 hashtags
 "characters": [{"name": str, "visual": str}],  # stable visual descriptor, reused verbatim in every shot
 "scenes": [{"id": int, "setting": str, "action": str, "subtitle": str, "mood": str}]}"""


def write_screenplay(logline: str, ledger: Ledger, on_delta=None, thinking: bool = True) -> dict:
    return chat_json("screenplay", config.MODEL_WRITER, SYSTEM,
                     f"Logline: {logline}", ledger, on_delta=on_delta, thinking=thinking)
