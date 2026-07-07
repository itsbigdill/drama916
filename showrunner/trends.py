"""Trend scout — what the internet talks about right now, turned into film ideas.

One Qwen call with live web search returns trending topics + fictionalized,
moderation-safe loglines. Cached in memory so page loads never re-search.
"""

import time

from . import config
from .ledger import Ledger
from .llm import chat_json

_TTL = {"today": 6 * 3600, "week": 24 * 3600}
_cache: dict[str, tuple[float, list[dict]]] = {}

SYSTEM = """You are a short-form video content strategist. Search the web for what is
genuinely trending {scope} WORLDWIDE with a US/global lens — news, pop culture,
sports, tech, viral memes. Mix regions; avoid leaning on one country's media. Pick 6
DIVERSE topics that would make fun 15-60 second short films.

For each topic write a logline: a 2-3 sentence fictional mini-drama scenario INSPIRED
by the topic. Loglines must be filmable by an image/video model with strict content
moderation: NO real people's names, NO brands, NO violence or darkness, NOTHING
sexual/NSFW, NO politics, war or tragedy — upbeat, family-friendly fictional
characters and situations that clearly wink at the trend.

Reply ONLY JSON:
{{"trends": [{{"topic": "2-4 words", "why": "one short factual line on why it's hot now",
"logline": "2-3 sentence scenario"}}]}}"""


def fetch_trends(period: str = "today") -> list[dict]:
    period = period if period in _TTL else "today"
    hit = _cache.get(period)
    if hit and time.time() - hit[0] < _TTL[period]:
        return hit[1]

    scope = "TODAY" if period == "today" else "THIS WEEK"
    ledger = Ledger()
    data = chat_json(
        "trends", config.MODEL_PLANNER,
        SYSTEM.format(scope=scope),
        f"Today's date: {time.strftime('%B %d, %Y')}. Find what is trending {scope.lower()} "
        f"and turn it into 6 film loglines.",
        ledger, thinking=False, search=True)
    ledger.print_table()

    BLOCKED = ("erotic", "nude", "sex", "nsfw", "war", "death", "shooting",
               "violence", "politic", "election", "tragedy")
    trends = []
    for t in data.get("trends", [])[:6]:
        blob = (str(t.get("topic", "")) + " " + str(t.get("why", "")) +
                " " + str(t.get("logline", ""))).lower()
        if any(b in blob for b in BLOCKED):
            continue
        topic, why, logline = (str(t.get(k, "")).strip() for k in ("topic", "why", "logline"))
        if topic and logline:
            trends.append({"topic": topic[:48], "why": why[:110], "logline": logline[:400]})
    if trends:
        _cache[period] = (time.time(), trends)
    return trends
