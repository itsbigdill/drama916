"""Trend scout — what the internet talks about right now, turned into film ideas.

One Qwen call with live web search returns trending topics + fictionalized,
moderation-safe loglines. Cached in memory so page loads never re-search.
"""

import json
import threading
import time
from pathlib import Path

from . import config
from .ledger import Ledger
from .llm import chat_json

_TTL = {"today": 6 * 3600, "week": 24 * 3600}
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_FILE = Path(config.RUNS_DIR) / "trends_cache.json"
_refreshing: set[str] = set()
_rlock = threading.Lock()


def _load_disk():
    try:
        for k, v in json.loads(_CACHE_FILE.read_text()).items():
            _cache[k] = (v[0], v[1])
    except (OSError, ValueError):
        pass


def _save_disk():
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_cache))
    except OSError:
        pass


_load_disk()

SYSTEM = """You are a short-form video content strategist. Search the web for what is
happening and going viral {scope} in GLOBAL POP CULTURE. Return SPECIFIC, DATEABLE
moments the average person worldwide would recognize: movie/show premieres, music
drops and tours, sports finals, gaming launches, celebrity moments, internet memes
born days ago, viral challenges, seasonal culture (Halloween, festival season), a
space/weather event underway. e.g. "World Cup 2026", a film that premiered this week,
a meme everyone is posting.

HARD BANS — a topic is INVALID if it is any of these:
- niche tech / enterprise / dev news (software updates, framework releases, "SQL
  Server", cloud products, B2B) — nobody makes a TikTok drama about a database patch;
- region-locked bureaucracy or exams ("Gaokao", local civil-service tests, heritage
  digitization programs) — must be globally legible, not one country's inside baseball;
- generic evergreen themes ("AI video tools", "pet fashion", "summer stargazing",
  "urban farming") — if it could have been written any month of any year, it fails.
Every topic must be a thing people are ACTIVELY talking about right now AND has obvious
story juice (drama, comedy, romance, spectacle). If unsure, prefer entertainment.

For each topic write a logline: a 2-3 sentence fictional mini-drama scenario INSPIRED
by it. Loglines must pass strict image/video moderation: NO real people's names, NO
brands, NOTHING sexual, NO politics, war, violence or tragedy — upbeat, family-friendly
fictional characters that clearly wink at the event.

Reply ONLY JSON:
{{"trends": [{{"topic": "PILL LABEL, 2-3 words max (e.g. 'World Cup 2026', 'Fruit drama')",
"why": "one short line: what exactly happened and when",
"logline": "2-3 sentence scenario"}}]}}"""


def fetch_trends(period: str = "today") -> list[dict]:
    period = period if period in _TTL else "today"
    hit = _cache.get(period)
    if hit and time.time() - hit[0] < _TTL[period]:
        return hit[1]
    if hit and hit[1]:
        # stale-while-revalidate: віддаємо вчорашні пілюлі миттєво,
        # свіжі тихо підвантажуються фоном
        with _rlock:
            if period not in _refreshing:
                _refreshing.add(period)
                threading.Thread(target=_refresh, args=(period,), daemon=True).start()
        return hit[1]
    return _fetch_now(period)


def _refresh(period: str):
    try:
        _fetch_now(period)
    finally:
        with _rlock:
            _refreshing.discard(period)


def _fetch_now(period: str) -> list[dict]:

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
    # niche/region topics the model still slips in despite the prompt
    NICHE = ("sql", "server update", "framework", "kubernetes", "database", "api ",
             "gaokao", "civil service", "heritage digitali", "b2b", "enterprise",
             "patch notes", "changelog", "devops", "compiler")

    def _pill(topic: str) -> str:  # <=26 chars, never cut mid-word
        topic = topic.strip()
        if len(topic) <= 26:
            return topic
        cut = topic[:26].rsplit(" ", 1)[0]
        return cut or topic[:26]

    trends = []
    for t in data.get("trends", [])[:6]:
        blob = (str(t.get("topic", "")) + " " + str(t.get("why", "")) +
                " " + str(t.get("logline", ""))).lower()
        if any(b in blob for b in BLOCKED) or any(b in blob for b in NICHE):
            continue
        topic, why, logline = (str(t.get(k, "")).strip() for k in ("topic", "why", "logline"))
        if topic and logline:
            trends.append({"topic": _pill(topic), "why": why[:110], "logline": logline[:400]})
    if trends:
        _cache[period] = (time.time(), trends)
        _save_disk()
    return trends
