"""Logline -> screenplay JSON."""

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM = """You are an award-winning short-form screenwriter. Given a logline you
write a complete screenplay for a ~45 second VERTICAL short DRAMA. The film is
VOICED: the characters SPEAK their lines aloud (there are no on-screen subtitles),
so write real dialogue, not narration.
Keep EVERY character the logline names — never drop one to simplify the story.
Each scene carries exactly ONE spoken line, attributed to the character who says
it. Give every character a gender so their line can be voiced correctly.
Reply ONLY with JSON:
{"title": str, "logline": str, "style": str,  # one reusable visual style sentence
 "caption": str,  # TikTok caption: one hook line under 100 chars, then 4 hashtags
 "characters": [{"name": str, "gender": "male"|"female"|"neutral", "visual": str}],
 # visual MUST be visually unambiguous — a simple, single-reading body plan.
 # No hybrid or paradoxical anatomy ("a seed for an eye", "half-human half-X",
 # "upper body human-like"): an image model resolves ambiguity differently in
 # every shot and the character falls apart. Distinct colors/props are welcome.
 "scenes": [{"id": int, "setting": str, "action": str,
             "speaker": str,     # the character NAME who speaks this scene's line
             "subtitle": str,    # their spoken line (short, punchy, emotional — this is voiced)
             "mood": str}]}"""


def write_screenplay(logline: str, ledger: Ledger, on_delta=None, thinking: bool = True) -> dict:
    return chat_json("screenplay", config.MODEL_WRITER, SYSTEM,
                     f"Logline: {logline}", ledger, on_delta=on_delta, thinking=thinking)
