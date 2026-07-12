"""Trend scout v2 — REAL trends in, film ideas out.

The v1 weakness: one search call asked for 6 topics, search returned one
query's worth of reality, and the model padded the rest with plausible filler
("Anime Hair Boom") that then stuck in the cache for hours.

v2 pipeline:
  1. SEEDS   — Google Trends RSS (live, no keys): real trending searches with
               traffic counts. The model can no longer invent trends — it
               curates a list that came from outside.
  2. FAN-OUT — three parallel Qwen calls with forced web search, each owning a
               narrow angle (screen/music · sports/events · memes/gaming), each
               grounded by the seed list. No single call needs to "fill six".
  3. VERIFY  — one cheap flash call scores every candidate: real, dateable,
               globally recognizable? Filler dies here.
  4. GUARDS  — moderation/niche blocklists, diversity rule (max 1 topic per
               leading keyword), and a single re-roll if fewer than 4 survive.

Cached in memory + disk with stale-while-revalidate, so page loads never wait.
"""

import json
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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

# ————— 1. SEEDS: Google Trends RSS — real trending searches, no keys —————

_RSS_URL = "https://trends.google.com/trending/rss?geo=US"


def _google_seeds(limit: int = 20) -> list[str]:
    """Live trending searches with traffic counts, e.g. 'arizona diamondbacks (2000+)'.
    Empty list on any failure — the fan-out then relies on web search alone."""
    try:
        req = urllib.request.Request(_RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        items = re.findall(
            r"<item>.*?<title>(.*?)</title>.*?(?:<ht:approx_traffic>(.*?)</ht:approx_traffic>)?.*?</item>",
            xml, re.S)
        seeds = []
        for title, traffic in items[:limit]:
            title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", title).strip()
            if title:
                seeds.append(f"{title} ({traffic.strip()})" if traffic.strip() else title)
        return seeds
    except Exception:
        return []


# ————— 2. FAN-OUT: three narrow angles, each grounded by the seeds —————

ANGLES = [
    ("screen & music", "movies, TV shows, streaming premieres, music drops, album releases, concert tours"),
    ("sports & spectacle", "sports finals and matches, live events, festivals, seasonal culture, space or weather spectacles"),
    ("internet & gaming", "internet memes born days ago, viral challenges, celebrity moments, gaming launches and updates"),
]

ANGLE_SYSTEM = """You are a short-form video content strategist scouting ONE beat:
{beat}. Search the web for what is happening {scope} in that beat, in GLOBAL pop
culture. At most ONE topic per real-world franchise/league/person — two takes on
the same thing is padding.

Return up to 3 topics. Every topic MUST be a real, dateable moment people are
actively talking about {scope} — if you cannot confirm a topic is real, DO NOT
include it. Fewer, real topics beat more, invented ones. NEVER pad the list.

Topic must be globally legible (no one country's inside baseball, no niche tech/
enterprise news, no evergreen themes that fit any month of any year).

For each topic write a logline: a 2-3 sentence fictional mini-drama scenario
INSPIRED by it. Loglines must pass strict image/video moderation: NO real people's
names, NO brands, NOTHING sexual, NO politics, war, violence or tragedy — upbeat,
family-friendly fictional characters that clearly wink at the event.

Reply ONLY JSON:
{{"trends": [{{"topic": "PILL LABEL, 2-3 words max",
"why": "one short line: what exactly happened and when",
"logline": "2-3 sentence scenario"}}]}}"""


def _angle_fetch(beat: str, scope: str, ledger: Ledger) -> list[dict]:
    try:
        data = chat_json(
            f"trends_{beat.split()[0]}", config.MODEL_PLANNER,
            ANGLE_SYSTEM.format(beat=beat, scope=scope),
            f"Today's date: {time.strftime('%B %d, %Y')}.\n"
            f"Scout your beat and return up to 3 REAL topics as loglines.",
            ledger, thinking=False, search=True)
        return list(data.get("trends", []))[:3]
    except Exception:
        return []  # one dead angle must not kill the ribbon


# Окремий куратор насінин: РЕАЛЬНІ трендові запити Google → максимум 2 глобально
# зрозумілі поп-культурні моменти. Ніша (локальний спорт, чиїсь прізвища без
# контексту) чесно пропускається — краще нуль, ніж натяжка.
SEED_SYSTEM = """You are a short-form video content strategist. Below are REAL trending
Google searches right now. Pick AT MOST 2 that are globally legible POP-CULTURE moments
(a movie, a music drop, a viral moment, a global sports final — not a regular-season
game, not a local athlete's stat line, not one country's inside baseball). Use web
search to confirm what exactly happened. If none qualify, return an empty list — do
NOT force-fit.

For each pick write a logline: a 2-3 sentence fictional mini-drama scenario INSPIRED
by it, moderation-safe: NO real people's names, NO brands, NOTHING sexual, NO politics,
war, violence or tragedy — upbeat, family-friendly fictional characters that wink at
the event.

Reply ONLY JSON:
{"trends": [{"topic": "PILL LABEL, 2-3 words max",
"why": "one short line: what exactly happened and when",
"logline": "2-3 sentence scenario"}]}"""


def _seed_fetch(seeds: list[str], ledger: Ledger) -> list[dict]:
    if not seeds:
        return []
    try:
        data = chat_json(
            "trends_seeds", config.MODEL_PLANNER, SEED_SYSTEM,
            f"Today's date: {time.strftime('%B %d, %Y')}.\nTrending searches:\n" +
            "\n".join(f"- {s}" for s in seeds),
            ledger, thinking=False, search=True)
        return list(data.get("trends", []))[:2]
    except Exception:
        return []


# ————— 3. VERIFY: one flash call kills the filler —————

VERIFY_SYSTEM = """You are a picky short-form content editor. Today is {date}. The
candidate topics below were found via live web search (assume they exist). Judge FORM,
not truth, for each:
- score 0-10: is it a SPECIFIC, DATEABLE moment with obvious story juice — or generic
  filler that could have been written any month of any year ("anime cafes are popular",
  "phone cases are trending" = 0-3)? Also low if the "why" describes something months
  old rather than around now, or something only one country would recognize
  (a regular-season game or one athlete's stat line = low; a final, a premiere,
  a global meme = high).
- dup: true if another topic covers the same underlying event/franchise/league/person
  (keep the strongest one as dup:false).
Reply ONLY JSON: {{"scores": [{{"i": index, "score": 0-10, "dup": false}}]}}"""


def _verify(cands: list[dict], ledger: Ledger) -> list[dict]:
    if not cands:
        return []
    listing = "\n".join(f"{i}: {c.get('topic', '')} — {c.get('why', '')}" for i, c in enumerate(cands))
    try:
        data = chat_json("trends_verify", config.MODEL_CHEAP,
                         VERIFY_SYSTEM.format(date=time.strftime("%B %d, %Y")),
                         listing, ledger, thinking=False)
        keep = {int(s["i"]) for s in data.get("scores", [])
                if not s.get("dup") and float(s.get("score", 0)) >= 6}
        return [c for i, c in enumerate(cands) if i in keep]
    except Exception:
        return cands  # verifier down → let the blocklists do their best


# ————— 4. GUARDS + assembly —————

BLOCKED = ("erotic", "nude", "sex", "nsfw", "war", "death", "shooting",
           "violence", "politic", "election", "tragedy")
NICHE = ("sql", "server update", "framework", "kubernetes", "database", "api ",
         "gaokao", "civil service", "heritage digitali", "b2b", "enterprise",
         "patch notes", "changelog", "devops", "compiler")
_STOP = {"the", "a", "an", "new", "big", "great"}


def _pill(topic: str) -> str:  # <=26 chars, never cut mid-word
    topic = topic.strip()
    if len(topic) <= 26:
        return topic
    cut = topic[:26].rsplit(" ", 1)[0]
    return cut or topic[:26]


def _lead_word(topic: str) -> str:
    for w in re.findall(r"[a-z0-9]+", topic.lower()):
        if w not in _STOP:
            return w
    return topic.lower()


def _clean(cands: list[dict]) -> list[dict]:
    """Moderation/niche blocklists + max 1 topic per leading keyword."""
    out, seen_lead = [], set()
    for t in cands:
        topic, why, logline = (str(t.get(k, "")).strip() for k in ("topic", "why", "logline"))
        if not topic or not logline:
            continue
        blob = f"{topic} {why} {logline}".lower()
        if any(b in blob for b in BLOCKED) or any(b in blob for b in NICHE):
            continue
        lead = _lead_word(topic)
        if lead in seen_lead:
            continue  # three 'Anime …' pills → one
        seen_lead.add(lead)
        out.append({"topic": _pill(topic), "why": why[:110], "logline": logline[:400]})
    return out


def _fetch_now(period: str) -> list[dict]:
    scope = "TODAY" if period == "today" else "THIS WEEK"
    ledger = Ledger()

    def one_round() -> list[dict]:
        seeds = _google_seeds()
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_angle_fetch, a[0], a[1] + f" ({scope.lower()})", ledger)
                    for a in ANGLES]
            futs.append(ex.submit(_seed_fetch, seeds, ledger))
            batches = [f.result() for f in futs]
        cands = [t for b in batches for t in b]
        return _clean(_verify(cands, ledger))

    trends = one_round()
    if len(trends) < 4:  # weak batch → ONE re-roll, never cache thin air
        # злиття теж іде через _clean: lead-word гард ловить "Wimbledon Finals"
        # проти "Wimbledon Women's Final" — точні рядки тут не працюють
        trends = _clean(trends + one_round())
    trends = trends[:6]
    ledger.print_table()

    if trends:
        _cache[period] = (time.time(), trends)
        _save_disk()
    return trends


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
