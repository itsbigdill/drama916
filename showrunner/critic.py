"""Director-critic loop: iterate on the shot list while it is still cheap text.

This is the token-budget-optimization core: a video clip costs ~$1, a critique
round costs ~$0.002. We converge on paper, then render once.
"""

import json

from . import config
from .ledger import Ledger
from .llm import chat_json

SYSTEM = """You are a ruthless film director reviewing a storyboard BEFORE an
expensive video-generation run. Score 1-10 and list concrete fixes for:
1) visual continuity (character/style descriptors identical across shots?),
2) narrative clarity for a first-time viewer reading only subtitles,
3) renderability (would a t2v model fail this? crowds, hands, physics, text?),
4) waste (shots that can be cut without losing the story).
When you reassign a line to a different character, UPDATE that shot's `speaker` and
`characters` to match — the wrong speaker gets the wrong voice.
Reply ONLY with JSON:
{"score": int, "verdict": str, "fixes": [{"shot_id": int, "problem": str, "fix": str}],
 "revised_shots": [...same schema as input INCLUDING scene_id, speaker, characters,
   action — only if score < 8...]}"""


def refine(shots: dict, ledger: Ledger, progress=None,
           max_rounds: int = config.MAX_CRITIC_ROUNDS) -> tuple[dict, list[dict]]:
    """Run up to MAX_CRITIC_ROUNDS; return (approved_shots, critique_history)."""
    history = []
    current = shots
    for round_no in range(1, max_rounds + 1):
        review = chat_json(f"critic_r{round_no}", config.MODEL_PLANNER, SYSTEM,
                           json.dumps(current, ensure_ascii=False), ledger, thinking=False)
        history.append(review)
        if progress:
            progress(round_no, review)
        if review.get("score", 0) >= 8:
            break
        if review.get("revised_shots"):
            current = {"shots": review["revised_shots"]}
    return current, history
