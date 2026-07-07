"""Showrunner web UI — one glass page: logline in, film out.

    python web.py            # http://localhost:8090

Stdlib-only server (no new deps). One run at a time (it's a demo, not a farm).
"""

import json
import threading
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from showrunner import pipeline  # noqa: E402

PORT = 8090

# single-run job state, updated by the pipeline's progress callback
state = {"running": False, "stage": "idle", "detail": "", "video": None,
         "cost": None, "error": None, "title": "", "caption": "", "log": {},
         "board": None, "run_id": 0,
         "live": {"script": None, "stills": [], "critic": [], "dailies": []}}
lock = threading.Lock()
# one approve Event PER RUN: an abandoned run keeps waiting on its own dead
# event and can never sneak into the paid FILM stage.
current_approve = {"ev": threading.Event(), "edits": {"drop": set()}}


def start_run(logline: str, dry_run: bool, vertical: bool,
              shots_target: int = 12, genre: str = "", cast: str = "", uid: str = ""):
    with lock:
        state["run_id"] += 1
        my_run = state["run_id"]
    my_event = threading.Event()
    my_edits = {"drop": set()}
    current_approve["ev"] = my_event
    current_approve["edits"] = my_edits

    def approval():
        my_event.wait()
        return {"drop": sorted(my_edits["drop"])}

    def cb(stage: str, detail: str):
        with lock:
            if state["run_id"] != my_run:
                return  # a Start over happened; this run is orphaned
            if stage.endswith("_live"):
                obj = json.loads(detail)
                if stage == "script_live":
                    state["live"]["script"] = obj
                elif stage == "still_live":
                    state["live"]["stills"].append(obj)
                elif stage == "critic_live":
                    state["live"]["critic"].append(obj)
                elif stage == "dailies_live":
                    state["live"]["dailies"].append(obj)
                return
            if stage == "approve":
                state["stage"] = "approve"
                state["board"] = json.loads(detail)
                return
            if stage == "done":
                d = json.loads(detail)
                try:  # фільм готовий — підписуємо ран власником для My videos
                    (Path(d["video"]).parent / "owner.txt").write_text(state.get("uid") or "")
                except OSError:
                    pass
                state.update(stage="done", detail="", cost=str(d["cost"]),
                             caption=d.get("caption", ""),
                             video="/video?p=" + d["video"], running=False)
                return
            state["stage"] = stage
            if not detail:
                state["detail"] = ""
                return
            # stage-completion reports arrive as JSON; live progress as plain text
            try:
                obj = json.loads(detail)
            except ValueError:
                state["detail"] = detail
                return
            state["log"][stage] = obj
            if stage == "script":
                state["title"] = obj.get("title", "")
            state["detail"] = ""

    def job():
        try:
            pipeline.run(logline, dry_run=dry_run, cb=cb, vertical=vertical,
                         approval=approval,
                         shots_target=shots_target, genre=genre, cast=cast)
        except BaseException as e:  # SystemExit included (budget cap)
            with lock:
                if state["run_id"] == my_run:
                    state.update(error=str(e), running=False, stage="error")

    with lock:
        state.update(running=True, stage="script", detail="", video=None,
                     cost=None, error=None, title="", caption="", log={}, board=None, uid=uid,
                     live={"script": None, "stills": [], "critic": [], "dailies": []})
    threading.Thread(target=job, daemon=True).start()


PAGE_TEMPLATE = r"""<!doctype html><meta charset="utf-8"><title>showrunner</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; font: 16px/1.5 -apple-system, system-ui;
         color: #22213A; background: #F7F7FC; display: flex; flex-direction: column;
         align-items: center; padding: 48px 18px; overflow-x: hidden; }
  body::before { content: ""; position: fixed; inset: 0; z-index: -1; background:
    radial-gradient(55% 40% at 12% 5%, rgba(108,92,231,.10), transparent 70%),
    radial-gradient(45% 40% at 90% 12%, rgba(160,140,255,.08), transparent 70%),
    radial-gradient(70% 50% at 50% 108%, rgba(108,92,231,.06), transparent 70%); }
  .mono { font-family: "JetBrains Mono", monospace; }
  .wordmark { font-family: "Unbounded", system-ui; font-weight: 800; font-size: 28px;
              letter-spacing: -.02em; margin-bottom: 26px; color: #26244a; }
  .dot { color: #6C5CE7; }
  #panes { width: 100%; max-width: 600px; display: flex; flex-direction: column; gap: 18px; }
  .glass { width: 100%; border-radius: 28px; padding: 22px;
           background: rgba(255,255,255,.82);
           border: 1px solid #EAE8F6;
           backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
           box-shadow: 0 24px 70px rgba(90,70,200,.12), 0 3px 10px rgba(34,33,58,.05),
                       inset 0 1px 0 #FFFFFF; }
  textarea { width: 100%; border: 1px solid transparent; resize: none; background: #FDFDFF;
             border-radius: 16px; padding: 15px 18px; font-size: 17px; line-height: 1.5;
             font-family: inherit; color: inherit; outline: none; min-height: 74px;
             box-shadow: inset 0 0 0 1px #F0EEF9;
             transition: border-color .2s, box-shadow .25s; }
  textarea:focus { border-color: #B9AFFF; box-shadow: 0 0 0 4px rgba(108,92,231,.12); }
  textarea::placeholder { color: #A9A6C6; }
  textarea.invalid { border-color: #E5484D; box-shadow: 0 0 0 4px rgba(229,72,77,.14);
                     animation: shake .35s ease; }
  @keyframes shake { 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
  .row { display: flex; gap: 10px; align-items: stretch; margin-top: 16px; }
  .trhead { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; }
  .trtabs { display: inline-flex; border: 1px solid #E7E5F3; border-radius: 10px; overflow: hidden; background: #F4F3FA; }
  .trtab { border: 0; background: transparent; cursor: pointer; padding: 5px 12px;
           font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700; color: #8B88AC; }
  .trtab.on { background: #ECE9FF; color: #5646D6; }
  .trrow { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
  .tpill { background: #F4F3FA; border: 1px solid #E7E5F3; border-radius: 999px;
           padding: 8px 15px; cursor: pointer; font-size: 13px; font-weight: 600;
           color: #454363; transition: transform .1s, border-color .2s, background .2s; }
  .tpill:hover { border-color: #C9BFFF; background: #ECE9FF; color: #5646D6; }
  .tpill:active { transform: scale(.95); }
  .tskel { width: 110px; height: 34px; border-radius: 999px; background: #F4F3FA;
           border: 1px solid #E7E5F3; animation: skel 1.1s ease-in-out infinite; }
  @keyframes skel { 50% { opacity: .45; } }
  textarea.flash { border-color: #B9AFFF; box-shadow: 0 0 0 4px rgba(108,92,231,.18); }
  .opts { display: flex; flex-wrap: wrap; gap: 12px 18px; margin-top: 14px; }
  .opt { display: flex; flex-direction: column; gap: 6px; }
  .ol { font-family: "JetBrains Mono", monospace; font-size: 10px; font-weight: 700;
        letter-spacing: .14em; text-transform: uppercase; color: #B4B1CF; padding-left: 3px; }
  .seg { display: inline-flex; gap: 0; border-radius: 12px; overflow: hidden;
         border: 1px solid #E7E5F3; background: #F4F3FA; }
  .seg .chip { border: 0; border-radius: 0; padding: 8px 13px; }
  .seg .chip + .chip { border-left: 1px solid #E7E5F3; }
  .chip { cursor: pointer; background: transparent; color: #8B88AC;
          font-family: "JetBrains Mono", monospace; font-size: 12.5px; font-weight: 700;
          transition: background .18s, color .18s, transform .1s; }
  .chip:active { transform: scale(.94); }
  .chip.on { background: #ECE9FF; color: #5646D6; box-shadow: inset 0 0 0 1px #C9BFFF; }
  .go { flex: 1; border: 0; border-radius: 16px; padding: 14px; cursor: pointer;
        background: linear-gradient(180deg, #7A5CFF, #5B45E0);
        color: #FFFFFF; font-family: "Unbounded", system-ui; font-weight: 800;
        font-size: 15px; letter-spacing: .12em; text-transform: uppercase;
        box-shadow: 0 16px 36px rgba(108,92,231,.35), inset 0 1px 0 rgba(255,255,255,.35);
        transition: transform .15s ease; }
  .go:hover { transform: translateY(-2px); filter: brightness(1.06); }
  .go:active { transform: translateY(0); filter: brightness(.97); }
  .go:disabled { opacity: .4; box-shadow: none; transform: none; }

  #steps { display: none; justify-content: space-between; margin: 26px 4px 0; }
  .step { text-align: center; flex: 1; font-family: "JetBrains Mono", monospace;
          font-size: 11px; font-weight: 700; letter-spacing: .14em; color: #B9B7D2; }
  .step .d { width: 13px; height: 13px; border-radius: 50%; margin: 0 auto 8px;
             background: #E4E2F1; }
  .step.on { color: #4232C8; }
  .step.on .d { background: radial-gradient(circle at 35% 30%, #B4A6FF, #5B45E0);
                box-shadow: 0 0 0 4px rgba(108,92,231,.16), 0 0 18px rgba(108,92,231,.85);
                animation: pulse 1.2s ease-in-out infinite; }
  .step.done { color: #55536E; }
  .step.done .d { background: radial-gradient(circle at 35% 30%, #FFF, #A8A5C8);
                  box-shadow: inset 0 1px 1px #FFF; }
  @keyframes pulse { 50% { transform: scale(1.4); } }
  #detail { text-align: center; font-family: "JetBrains Mono", monospace; font-size: 12.5px;
            color: #8B88AC; margin-top: 12px; min-height: 18px; }

  #runPane { display: none; }
  #panes.running #runPane { display: block; animation: rise .5s cubic-bezier(.22,.8,.3,1); }
  @keyframes rise { from { transform: translateY(18px); opacity: 0; } }
  .runglass { background: rgba(252,252,255,.92);
              box-shadow: 0 24px 70px rgba(90,70,200,.16), 0 3px 10px rgba(34,33,58,.05),
                          inset 0 1px 0 #FFFFFF; }
  .runhead { display: flex; justify-content: space-between; align-items: center;
             padding-bottom: 12px; border-bottom: 1px solid #EDEBF7; margin-bottom: 4px; }
  #runTitle { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 15px;
              color: #26244A; }
  #panes.running #formPane { opacity: .92; }
  #beacon { width: 70px; height: 70px; margin: 14px auto 6px; position: relative; display: none; }
  #beacon .core { position: absolute; inset: 21px; border-radius: 50%;
                  background: radial-gradient(circle at 35% 30%, #A897FF, #6C5CE7);
                  box-shadow: 0 0 26px rgba(108,92,231,.7); animation: recp 1.1s ease-in-out infinite; }
  #beacon::before, #beacon::after { content: ""; position: absolute; inset: 0; border-radius: 50%;
                  border: 1px solid rgba(108,92,231,.35); animation: ring 2.2s linear infinite; }
  #beacon::after { animation-delay: 1.1s; }
  @keyframes recp { 50% { transform: scale(1.18); } }
  @keyframes ring { 0% { transform: scale(.55); opacity: 1; } 100% { transform: scale(1.35); opacity: 0; } }
  #mock { display: none; text-align: center; font-family: "JetBrains Mono", monospace;
          font-size: 12px; color: #A9A6C6; min-height: 17px; margin-bottom: 4px; }
  #boardgrid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 16px; }
  .bcell { position: relative; }
  .bcell img { width: 100%; border-radius: 12px; display: block;
               box-shadow: 0 10px 24px rgba(90,70,200,.18); }
  .bfall { border: 1.5px dashed #D9D5EE; border-radius: 12px; background: #FBFAFF; }
  #boardgrid.v916 .bfall { aspect-ratio: 9/16; }
  #boardgrid.v169 .bfall { aspect-ratio: 16/9; }
  .bcell .bp { font-size: 11px; color: #A19FBE; margin-top: 3px; line-height: 1.35; }
  .bcell .bn { position: absolute; top: 6px; left: 6px; background: rgba(255,255,255,.92);
               color: #5646D6; font-family: "JetBrains Mono", monospace; font-size: 10.5px;
               font-weight: 700; border-radius: 8px; padding: 2px 7px; }
  .bcell .bs { font-size: 11.5px; color: #6B6890; margin-top: 5px; line-height: 1.35; }
  #shotlist { margin-top: 14px; }
  .shot { display: flex; gap: 12px; align-items: baseline; padding: 9px 4px;
          border-top: 1px solid #EDEBF7; }
  .shot .sn { font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700;
              color: #6C5CE7; flex: 0 0 26px; }
  .shot .st { font-size: 14px; color: #454363; }
  .shot .sp { font-size: 12px; color: #A19FBE; display: block; margin-top: 1px; }
  #live:empty { display: none; }
  .lcon { background: #F4F3FA; border-radius: 12px; padding: 10px 13px; margin-top: 12px;
          font-family: "JetBrains Mono", monospace; font-size: 11px; line-height: 1.55;
          color: #55536E; max-height: 150px; overflow: hidden; white-space: pre-wrap;
          word-break: break-word; display: flex; flex-direction: column-reverse; }
  .lcon.dim { color: #A9A6C6; font-style: italic; }
  .llab { font-family: "JetBrains Mono", monospace; font-size: 10px; font-weight: 700;
          letter-spacing: .14em; text-transform: uppercase; color: #B4B1CF;
          margin: 12px 0 0 3px; }
  .lline { font-family: "JetBrains Mono", monospace; font-size: 12px; color: #55536E;
           padding: 6px 3px; border-top: 1px solid #EDEBF7; }
  .lline b { color: #5646D6; }
  .lthumbs { display: flex; gap: 7px; flex-wrap: wrap; margin-top: 10px; }
  .lthumbs img { width: 52px; height: 74px; object-fit: cover; border-radius: 9px;
                 box-shadow: 0 6px 14px rgba(90,70,200,.16); animation: pop .3s ease; }
  @keyframes pop { 0% { transform: scale(.6); opacity: 0; } }
  #feed { margin-top: 6px; display: none; }
  .fblk { border-top: 1px solid #EDEBF7; padding: 4px 0; }
  .fblk summary { list-style: none; cursor: pointer; display: flex; gap: 12px;
                  align-items: baseline; padding: 8px 4px; }
  .fblk summary::-webkit-details-marker { display: none; }
  .fblk .fl { font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700;
              letter-spacing: .12em; color: #6C5CE7; flex: 0 0 64px; }
  .fblk .fv { font-size: 14.5px; color: #33314E; }
  .fblk .fv b { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 13.5px; }
  .fbody { padding: 2px 4px 10px 76px; }
  .scene { font-size: 13px; color: #55536E; padding: 5px 0; border-top: 1px dashed #EFEDF8; }
  .scene:first-child { border-top: 0; }
  .scene .sn { font-family: "JetBrains Mono", monospace; font-size: 10.5px; font-weight: 700;
               color: #A08CFF; margin-right: 7px; }
  .scene .sset { font-weight: 600; color: #454363; }
  .scene .ssub { color: #8B88AC; font-style: italic; }
  .ffix { color: #6C5CE7; }
  .gwrap { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
           gap: 10px; margin-top: 14px; }
  .gcell { position: relative; border-radius: 14px; overflow: hidden; }
  .gcell img { width: 100%; height: 150px; object-fit: cover; display: block;
               filter: saturate(.35) brightness(1.12) blur(2px); opacity: .68; }
  .gcell::after { content: ""; position: absolute; inset: 0;
    background: linear-gradient(115deg, transparent 35%, rgba(255,255,255,.75) 50%, transparent 65%);
    background-size: 240% 100%; animation: frost 2.4s linear infinite; }
  .gcell:nth-child(3n+2)::after { animation-delay: .5s; }
  .gcell:nth-child(3n)::after { animation-delay: 1s; }
  @keyframes frost { from { background-position: 130% 0; } to { background-position: -130% 0; } }
  .fnote { font-family: "JetBrains Mono", monospace; font-size: 11.5px; color: #8B88AC;
           padding: 3px 0; }
  .fthumbs { display: flex; gap: 7px; flex-wrap: wrap; padding-top: 4px; }
  .fthumbs img { width: 52px; height: 74px; object-fit: cover; border-radius: 9px;
                 box-shadow: 0 6px 14px rgba(90,70,200,.16); }

  #cinema { display: none; margin-top: 22px; }
  #cinema video { width: 100%; max-height: 64vh; object-fit: contain; background: #0E0D18;
                  border-radius: 20px; display: block;
                  box-shadow: 0 22px 54px rgba(34,33,58,.28); }
  #cap { font-size: 14px; color: #55536E; background: #F4F3FA;
         border-radius: 14px; padding: 13px 16px; margin: 14px 0 2px; white-space: pre-wrap; }
  #cap:empty { display: none; }
  a.chip { text-decoration: none; display: inline-flex; align-items: center;
           border: 1px solid #E7E5F3; border-radius: 12px; background: #F4F3FA; padding: 10px 16px; }
  #title { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 22px;
           margin: 16px 2px 2px; color: #26244A; }
  #meta { font-family: "JetBrains Mono", monospace; font-size: 12px; color: #8B88AC; margin: 4px 2px; }
  .ghost { border: 0; background: transparent; cursor: pointer; padding: 0 8px;
           color: #8B88AC; font: 700 13px -apple-system, system-ui; }
  #err { display: none; margin-top: 16px; font-size: 14px; color: #E5484D; }
  .bx { position: absolute; top: 8px; right: 8px; display: flex; gap: 6px; z-index: 2; }
  .bbtn { width: 28px; height: 28px; border: 0; border-radius: 50%; cursor: pointer;
          background: rgba(255,255,255,.92); color: #454363; font-size: 14px; line-height: 1;
          box-shadow: 0 4px 12px rgba(34,33,58,.22); transition: transform .12s; }
  .bbtn:hover { transform: scale(1.12); }
  .bbtn:disabled { opacity: .35; transform: none; }
  .bscene { font-size: 11.5px; line-height: 1.45; color: #8B88AC; margin-top: 5px; }
  .bscene b { color: #55536E; font-weight: 600; }
  .bcell.rf img { filter: saturate(.35) brightness(1.12) blur(2px); opacity: .68; }
  .bcell.rf::after { content: ""; position: absolute; inset: 0; border-radius: inherit;
    background: linear-gradient(115deg, transparent 35%, rgba(255,255,255,.75) 50%, transparent 65%);
    background-size: 240% 100%; animation: frost 2.4s linear infinite; }
  #myvids { display: none; }
  .vh { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 15px; color: #26244A;
        padding-bottom: 12px; border-bottom: 1px solid #EDEBF7; }
  #vgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
           gap: 12px; margin-top: 16px; }
  .vcell { position: relative; border-radius: 16px; overflow: hidden; cursor: pointer;
           background: #0E0D18; box-shadow: 0 10px 26px rgba(34,33,58,.16); }
  .vcell img, .vcell video { width: 100%; height: 190px; object-fit: cover; display: block; }
  .vcell img { transition: transform .3s ease; }
  .vcell:hover img { transform: scale(1.04); }
  .vmeta { position: absolute; left: 0; right: 0; bottom: 0; padding: 22px 10px 8px;
           background: linear-gradient(transparent, rgba(14,13,24,.88)); color: #FFF;
           pointer-events: none; }
  .vt { font-size: 12.5px; font-weight: 700; line-height: 1.25; }
  .vc { font-family: "JetBrains Mono", monospace; font-size: 10px; opacity: .75; margin-top: 2px; }
  .vplay { position: absolute; top: 50%; left: 50%; width: 40px; height: 40px; margin: -20px 0 0 -20px;
           border-radius: 50%; background: rgba(255,255,255,.88); pointer-events: none;
           box-shadow: 0 6px 18px rgba(0,0,0,.3); }
  .vplay::after { content: ""; position: absolute; left: 16px; top: 12px;
                  border-left: 12px solid #26244A; border-top: 8px solid transparent;
                  border-bottom: 8px solid transparent; }
  .foot { margin-top: 26px; font-size: 12px; }
  .foot a { color: #A9A6C6; }
</style>
<body>
<div class="wordmark">showrunner<span class="dot">.</span></div>

<div id="panes">
  <div id="formPane" class="glass">
  <textarea id="log" placeholder="One line. A whole film."></textarea>
  <div class="trhead">
    <span class="ol">Trending</span>
    <span class="trtabs"><button class="trtab on" data-p="today">Today</button><button class="trtab" data-p="week">Week</button></span>
  </div>
  <div id="trends" class="trrow"></div>

  <div class="opts">
    <div class="opt"><span class="ol">Ratio</span><span class="seg" data-k="fmt"><button class="chip on" data-v="916">9:16</button><button class="chip" data-v="169">16:9</button></span></div>
    <div class="opt"><span class="ol">Length</span><span class="seg" data-k="len"><button class="chip" data-v="3">15s</button><button class="chip" data-v="6">30s</button><button class="chip" data-v="9">45s</button><button class="chip on" data-v="12">60s</button></span></div>
    <div class="opt"><span class="ol">Genre</span><span class="seg" data-k="genre"><button class="chip on" data-v="drama">Drama</button><button class="chip" data-v="comedy">Comedy</button><button class="chip" data-v="noir">Noir</button><button class="chip" data-v="comic book style">Comic</button><button class="chip" data-v="ad">Ad</button></span></div>
    <div class="opt"><span class="ol">Cast</span><span class="seg" data-k="cast"><button class="chip on" data-v="realistic human characters">Real</button><button class="chip" data-v="anthropomorphic fruit and vegetable characters">Fruits</button><button class="chip" data-v="animal characters">Animals</button><button class="chip" data-v="everyday objects brought to life as characters">Objects</button></span></div>
  </div>
  <div class="row">
    <button id="go" class="go">Action</button>
  </div>
  <div id="formErr" style="display:none;margin-top:12px;font-size:14px;color:#E5484D"></div>
  </div><!-- /formPane -->

  <div id="runPane" class="glass runglass">
  <div class="runhead">
    <span id="runTitle">Production</span>
    <button class="ghost" onclick="startOver()" title="close">✕</button>
  </div>
  <div id="beacon"><span class="core"></span></div>
  <div id="mock"></div>
  <div id="detail"></div>
  <div id="live"></div>
  <div id="steps">
    <div class="step" data-s="script"><div class="d"></div>SCRIPT</div>
    <div class="step" data-s="board"><div class="d"></div>BOARD</div>
    <div class="step" data-s="critic"><div class="d"></div>CRITIC</div>
    <div class="step" data-s="stills"><div class="d"></div>STILLS</div>
    <div class="step" data-s="film"><div class="d"></div>FILM</div>
    <div class="step" data-s="cut"><div class="d"></div>CUT</div>
  </div>
  <div id="feed"></div>
  <div id="dbg" style="margin-top:10px;font:10px/1.4 monospace;color:#C6C3DE"></div>

  <div id="board" style="display:none">
    <div id="shotlist"></div>
    <div class="row" style="margin-top:18px">
      <button id="film" class="go">Film it</button>
      <button class="ghost" onclick="startOver()">Start over</button>
    </div>
  </div>

  <div id="cinema">
    <video id="player" controls playsinline></video>
    <div id="title"></div>
    <div id="meta"></div>
    <div id="cap"></div>
    <div class="row">
      <a id="dl" class="chip" download="showrunner.mp4">Download</a>
      <button id="copycap" class="chip">Copy caption</button>
      <button class="ghost" onclick="startOver()" style="margin-left:auto">New film</button>
    </div>
  </div>
  <div id="err"></div>
  </div><!-- /runPane -->

  <div id="myvids" class="glass">
    <div class="vh">My videos</div>
    <div id="vgrid"></div>
  </div>
</div><!-- /panes -->

<div class="foot"><a href="https://www.qwencloud.com">Qwen + HappyHorse on Alibaba Cloud</a> · <span id="build">BUILD_STAMP</span></div>

<div id="jsErr" style="display:none;position:fixed;bottom:10px;left:10px;right:10px;z-index:99;background:#FDECEC;border:1px solid #F5B5B5;color:#B42318;border-radius:12px;padding:10px 14px;font:12px/1.4 monospace;word-break:break-all"></div>
<script>
var $ = function (id) { return document.getElementById(id); };
function reportErr(text) {
  try {
    var b = $("jsErr"); b.style.display = "block"; b.textContent = "\u26A0 " + text;
    fetch("/clientlog", { method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ err: String(text).slice(0, 500) }) }).catch(function(){});
  } catch (e) {}
}
window.onerror = function (msg, src, line, col, err) {
  reportErr(msg + " @" + line + ":" + col + (err && err.stack ? " || " + String(err.stack).split("\n").slice(0,2).join(" ") : ""));
};
window.addEventListener("unhandledrejection", function (e) {
  reportErr("promise: " + ((e.reason && (e.reason.stack || e.reason.message)) || e.reason));
});
function startOver() {
  fetch("/reset", { method: "POST" }).finally(function () { location.reload(); });
}
var ORDER = ["script", "board", "critic", "stills", "film", "cut"];
var t0 = null;

var uid = localStorage.getItem("sr_uid");
if (!uid) { uid = Math.random().toString(36).slice(2) + Date.now().toString(36);
            localStorage.setItem("sr_uid", uid); }
function loadVids() {
  fetch("/videos?uid=" + encodeURIComponent(uid)).then(function (r) { return r.json(); }).then(function (d) {
    var vids = d.videos || [];
    if (!vids.length) { $("myvids").style.display = "none"; return; }
    $("myvids").style.display = "block";
    $("vgrid").innerHTML = vids.map(function (v, i) {
      return '<div class="vcell" data-i="' + i + '">' +
             (v.poster ? '<img src="/video?p=' + encodeURIComponent(v.poster) + '" loading="lazy">'
                       : '<img alt="">') +
             '<span class="vplay"></span>' +
             '<div class="vmeta"><div class="vt">' + String(v.title || "Untitled").replace(/</g, "&lt;") + '</div>' +
             '<div class="vc">' + (v.cost != null ? "$" + (+v.cost).toFixed(2) : "") + '</div></div></div>';
    }).join("");
    $("vgrid").querySelectorAll(".vcell").forEach(function (c) {
      c.onclick = function () {
        var v = vids[+c.dataset.i];
        c.innerHTML = '<video controls autoplay playsinline src="/video?p=' +
                      encodeURIComponent(v.video) + '"></video>';
        c.onclick = null;
      };
    });
  }).catch(function () {});
}
loadVids();

function enterRun() {
  document.getElementById("panes").classList.add("running");
  $("steps").style.display = "flex"; $("feed").style.display = "block";
  $("beacon").style.display = "block"; $("mock").style.display = "block";
  if (!t0) t0 = Date.now();
  poll();
}
// рефреш не втрачає роботу: сервер пам'ятає ран — повертаємось у нього
window.addEventListener("load", function () {
  fetch("/status").then(function (r) { return r.json(); }).then(function (s) {
    if (s.stage && s.stage !== "idle") enterRun();
  });
});
var opts = { fmt: "916", len: "12", genre: "drama", cast: "realistic human characters" };
document.querySelectorAll(".seg").forEach(function (seg) {
  var k = seg.dataset.k;
  seg.querySelectorAll(".chip").forEach(function (ch) {
    ch.onclick = function () {
      seg.querySelectorAll(".chip").forEach(function (x) { x.classList.remove("on"); });
      ch.classList.add("on");
      opts[k] = ch.dataset.v;
    };
  });
});

// тренд-скаут: живі теми → тап вставляє логлайн
var trCache = {};
function renderTrends(list) {
  $("trends").innerHTML = list.map(function (tr, i) {
    return '<button class="tpill" data-i="' + i + '" title="' +
           (tr.why || "").replace(/"/g, "&quot;") + '">' + tr.topic + '</button>';
  }).join("");
  $("trends").querySelectorAll(".tpill").forEach(function (c) {
    c.onclick = function () {
      var tr = list[+c.dataset.i];
      var f = $("log");
      f.value = tr.logline;
      f.classList.add("flash");
      setTimeout(function () { f.classList.remove("flash"); }, 900);
    };
  });
}
function loadTrends(period) {
  if (trCache[period]) { renderTrends(trCache[period]); return; }
  $("trends").innerHTML = '<span class="tskel"></span><span class="tskel"></span><span class="tskel"></span><span class="tskel"></span>';
  fetch("/trends?period=" + period).then(function (r) { return r.json(); }).then(function (d) {
    trCache[period] = d.trends || [];
    renderTrends(trCache[period]);
  }).catch(function () { $("trends").innerHTML = ""; });
}
document.querySelectorAll(".trtab").forEach(function (b) {
  b.onclick = function () {
    document.querySelectorAll(".trtab").forEach(function (x) { x.classList.remove("on"); });
    b.classList.add("on");
    loadTrends(b.dataset.p);
  };
});
loadTrends("today");

// студійні рядки під маяком
var MOCKS = {
  script:  ["Waking the screenwriter…", "Chasing the third act…", "Sharpening pencils…"],
  board:   ["Taping storyboards to the wall…", "Counting the shots…"],
  critic:  ["The critic adjusts their glasses…", "Red ink everywhere…"],
  stills:  ["Casting is arguing about the lead…", "Painting frame by frame…", "Mixing the palette…"],
  film:    ["Quiet on set…", "Rolling…", "Craft services ran out of coffee…"],
  cut:     ["Splicing the reels…", "Syncing subtitles…"]
};
var mockIx = 0, mockStage = "script";
function setMockStage(st) { if (MOCKS[st]) mockStage = st; }
setInterval(function () {
  var m = $("mock");
  if (m.style.display !== "block") return;
  var list = MOCKS[mockStage] || MOCKS.script;
  mockIx = (mockIx + 1) % list.length;
  m.textContent = list[mockIx];
}, 2700);

// rotating idea placeholder
var IDEAS = [
  "A robot janitor on a space station finds a houseplant",
  "An aging boxer teaches his granddaughter to waltz",
  "A lighthouse keeper adopts a lost baby seagull",
  "Two rival street food vendors fall for the same customer",
  "A retired spy joins a suburban book club",
  "The last payphone on Earth starts ringing",
  "A grandma secretly races drones at night"
];
var ideaIx = 0;
setInterval(function () {
  if ($("log").value) return;
  ideaIx = (ideaIx + 1) % IDEAS.length;
  $("log").placeholder = "One line. A whole film.\n“" + IDEAS[ideaIx] + "”";
}, 3200);

$("go").onclick = function () {
  var logline = $("log").value.trim();
  if (logline.length < 8) {
    var f = $("log");
    f.classList.remove("invalid"); void f.offsetWidth;  // рестарт анімації
    f.classList.add("invalid"); f.focus();
    return;
  }
  $("log").classList.remove("invalid");
  $("go").disabled = true; $("log").disabled = true; t0 = Date.now();
  fetch("/run", { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ logline: logline, vertical: opts.fmt === "916", uid: uid,
                                         shots: +opts.len, genre: opts.genre, cast: opts.cast }) })
    .then(function (r) {
      if (!r.ok) {
        return r.json().then(function (e) {
          $("go").disabled = false; $("log").disabled = false;
          $("err").style.display = "block";
          $("err").textContent = e.error || "could not start";
        });
      }
      document.getElementById("panes").classList.add("running");
      $("steps").style.display = "flex"; $("feed").style.display = "block";
      $("beacon").style.display = "block"; $("mock").style.display = "block";
      poll();
    });
};

// incremental thumbnails: append only NEW frames so existing <img> nodes are
// never recreated \u2014 no re-fetch, no replayed pop animation, no blinking
function syncThumbs(el, mode, label, wrapCls, cellWrap, urls) {
  if (el.dataset.mode !== mode) {
    el.dataset.mode = mode;
    el.innerHTML = '<div class="llab">' + label + '</div><div class="' + wrapCls + '"></div>';
  }
  var box = el.querySelector("." + wrapCls);
  if (!box) return;
  var seen = {};
  Array.prototype.forEach.call(box.querySelectorAll("img"), function (img) {
    seen[img.getAttribute("data-key")] = 1;
  });
  urls.forEach(function (u) {
    if (!u || seen[u]) return;
    var img = document.createElement("img");
    img.setAttribute("data-key", u);
    img.decoding = "async";
    img.src = "/video?p=" + encodeURIComponent(u);
    if (cellWrap) {
      var cell = document.createElement("div");
      cell.className = "gcell";
      cell.appendChild(img);
      box.appendChild(cell);
    } else {
      box.appendChild(img);
    }
  });
}
function renderLive(s) {
  var L = s.live || {}, el = $("live");
  if (s.stage === "stills" && L.stills && L.stills.length) {
    syncThumbs(el, "stills", "storyboard", "lthumbs", false,
               L.stills.map(function (st) { return st.img; }));
    return;
  }
  if ((s.stage === "film" || s.stage === "cut") && s.board &&
      (s.board.shots || []).some(function (sh) { return sh.img; })) {
    syncThumbs(el, "grid-" + s.stage, s.stage === "cut" ? "assembling" : "filming",
               "gwrap", true, s.board.shots.map(function (sh) { return sh.img; }));
    return;
  }
  var h = "";
  if (s.stage === "script" && L.script && L.script.tail) {
    h = '<div class="llab">writer \u00B7 ' + (L.script.kind === "thinking" ? "thinking" : "writing") + '</div>' +
        '<div class="lcon' + (L.script.kind === "thinking" ? " dim" : "") + '">' +
        L.script.tail.replace(/</g, "&lt;") + '</div>';
  } else if ((s.stage === "critic" || s.stage === "board") && L.critic && L.critic.length) {
    h = '<div class="llab">critic</div>' + L.critic.map(function (r) {
      return '<div class="lline"><b>R' + r.round + " \u00B7 " + (r.score != null ? r.score + "/10" : "\u2014") + '</b>' +
             (r.fixes && r.fixes.length ? " \u2014 " + r.fixes.join("; ").replace(/</g, "&lt;") : " \u2014 approved") + '</div>';
    }).join("");
  }
  el.dataset.mode = "text";
  el.innerHTML = h;
}

function esc2(x) { return String(x == null ? "" : x).replace(/</g, "&lt;"); }
function blk(label, head, body, open) {
  return '<details class="fblk"' + (open ? " open" : "") + '><summary><span class="fl">' +
         label + ' \u2713</span><span class="fv">' + head + '</span></summary>' +
         (body ? '<div class="fbody">' + body + '</div>' : "") + '</details>';
}
function feedRows(s) {
  var L = s.log || {}, live = s.live || {}, h = "";
  if (L.script) {
    var scenes = Array.isArray(L.script.scenes) ? L.script.scenes : [];
    var sbody = scenes.map(function (sc) {
      return '<div class="scene"><span class="sn">' + esc2(sc.id) + '</span>' +
             '<span class="sset">' + esc2(sc.setting) + '</span> \u2014 ' + esc2(sc.action) +
             (sc.subtitle ? ' <span class="ssub">\u201C' + esc2(sc.subtitle) + '\u201D</span>' : "") + '</div>';
    }).join("");
    h += blk("SCRIPT", "<b>\u201C" + esc2(L.script.title) + "\u201D</b> \u00B7 " +
             (scenes.length || L.script.scenes) + " scenes", sbody,
             s.stage === "board" || s.stage === "critic");
  }
  if (L.board) {
    var shots = Array.isArray(L.board.shots) ? L.board.shots : [];
    var bbody = shots.map(function (sh) {
      return '<div class="scene"><span class="sn">' + String(sh.id).padStart(2, "0") + '</span>' +
             esc2(sh.prompt) + (sh.subtitle ? ' <span class="ssub">\u201C' + esc2(sh.subtitle) + '\u201D</span>' : "") + '</div>';
    }).join("");
    h += blk("BOARD", (shots.length || L.board.shots) + " shots planned", bbody, s.stage === "critic");
  }
  if (L.critic) {
    var cbody = (L.critic.verdict ? '<div class="fnote">' + esc2(L.critic.verdict) + '</div>' : "") +
                (L.critic.notes || []).map(function (n) {
                  if (typeof n === "string") return '<div class="fnote">\u2717 ' + esc2(n) + '</div>';
                  return '<div class="fnote">\u2717 ' + esc2(n.problem) +
                         (n.fix ? ' <span class="ffix">\u2192 ' + esc2(n.fix) + '</span>' : "") + '</div>';
                }).join("");
    var chead = L.critic.rewrote
        ? "draft " + (L.critic.score != null ? L.critic.score + "/10" : "rejected") +
          " \u2192 <b>rewrote the board</b>" + (L.critic.shots ? " \u00B7 " + L.critic.shots + " shots" : "")
        : (L.critic.score != null ? "score " + L.critic.score + "/10" : "approved") +
          " \u00B7 " + L.critic.rounds + " round" + (L.critic.rounds > 1 ? "s" : "") +
          (L.critic.shots ? " \u00B7 " + L.critic.shots + " shots final" : "");
    h += blk("CRITIC", chead, cbody, s.stage === "stills" || s.stage === "approve");
  }
  if (live.stills && live.stills.length && s.stage !== "stills") {
    h += blk("STILLS", live.stills.length + " frames painted",
             '<div class="fthumbs">' + live.stills.map(function (st) {
               return '<img src="/video?p=' + encodeURIComponent(st.img) + '">';
             }).join("") + "</div>", s.stage === "approve");
  }
  if (s.stage === "cut" || s.stage === "done") h += blk("FILM", "all shots rendered", "", false);
  $("feed").innerHTML = h;
}

function sceneOf(s, sh) {
  var scenes = (s.log && s.log.script && s.log.script.scenes) || [];
  for (var i = 0; i < scenes.length; i++)
    if (scenes[i].id === sh.scene_id) return scenes[i];
  return null;
}
function showBoard(s) {
  var b = s.board || {};
  var withImgs = (b.shots || []).some(function (sh) { return sh.img; });
  if (withImgs) {
    $("shotlist").innerHTML = '<div id="boardgrid" class="v' + opts.fmt + '">' + b.shots.map(function (sh, i) {
      var sc = sceneOf(s, sh);
      var scene = sc ? '<b>' + esc2(sc.setting) + '.</b> ' + esc2(sc.action)
                     : esc2((sh.prompt || "").split(". ").pop().slice(0, 90));
      return '<div class="bcell" data-id="' + sh.id + '"><span class="bn">' + String(sh.id).padStart(2, "0") + '</span>' +
        '<span class="bx"><button class="bbtn rd" title="redraw">\u21BB</button>' +
        '<button class="bbtn dr" title="remove">\u2715</button></span>' +
        (sh.img
          ? '<img src="/video?p=' + encodeURIComponent(sh.img) + '&t=' + Date.now() + '" ' +
            'onerror="this.outerHTML=\'<div class=&quot;bfall&quot;></div>\'">'
          : '<div class="bfall"></div>') +
        '<div class="bs">' + (sh.subtitle || "") + '</div>' +
        '<div class="bscene">' + scene + '</div></div>';
    }).join("") + "</div>";
    wireBoardCells(s);
  } else {
    $("shotlist").innerHTML = (b.shots || []).map(function (sh) {
      return '<div class="shot"><span class="sn">' + String(sh.id).padStart(2, "0") + '</span>' +
        '<span class="st">' + (sh.subtitle || "") +
        '<span class="sp">' + (sh.prompt || "").slice(0, 90) + '…</span></span></div>';
    }).join("");
  }
  $("film").textContent = b.estimate ? "Film it \u00B7 ~$" + Math.round(b.estimate) : "Film it";
  $("film").onclick = function () {
    this.disabled = true;
    t0 = Date.now();
    fetch("/approve", { method: "POST" }).then(function () {
      $("board").style.display = "none";
      $("beacon").style.display = "block"; $("mock").style.display = "block";
      poll();
    });
  };
  $("board").style.display = "block";
}

function wireBoardCells(s) {
  var cells = document.querySelectorAll ? document.querySelectorAll(".bcell") : [];
  cells.forEach(function (cell) {
    var id = +cell.dataset.id;
    var rd = cell.querySelector(".rd"), dr = cell.querySelector(".dr");
    if ((s.board.shots || []).length <= 1 && dr) dr.disabled = true;
    if (rd) rd.onclick = function () {
      if (cell.classList.contains("rf")) return;
      cell.classList.add("rf"); rd.disabled = true;
      fetch("/redraw", { method: "POST", headers: { "Content-Type": "application/json" },
                         body: JSON.stringify({ id: id }) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          cell.classList.remove("rf"); rd.disabled = false;
          if (res.ok) {
            var img = cell.querySelector("img");
            if (img) img.src = "/video?p=" + encodeURIComponent(res.d.img) + "&t=" + Date.now();
          } else { reportErr("redraw: " + (res.d.error || "failed")); }
        })
        .catch(function () { cell.classList.remove("rf"); rd.disabled = false; });
    };
    if (dr) dr.onclick = function () {
      fetch("/drop", { method: "POST", headers: { "Content-Type": "application/json" },
                       body: JSON.stringify({ id: id }) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.board) { s.board = d.board; showBoard(s); }
        }).catch(function () {});
    };
  });
}

function poll() {
  fetch("/status").then(function (r) { return r.json(); }).then(function (s) {
   try {
    var isApprove = s.stage === "approve";
    var idx = isApprove ? 4 : ORDER.indexOf(s.stage);
    document.querySelectorAll(".step").forEach(function (el, i) {
      el.className = "step" + (i < idx || s.stage === "done" ? " done"
        : (i === idx && !isApprove) ? " on" : "");
    });
    if (s.title) $("runTitle").textContent = "\u201C" + s.title + "\u201D";
    setMockStage(s.stage);
    renderLive(s);
    feedRows(s);
    var snap = "stage=" + s.stage + " feed=" + $("feed").innerHTML.length +
               " live=" + $("live").innerHTML.length + " logKeys=" + Object.keys(s.log || {}).join(",");
    $("dbg").textContent = snap;
    if (s.stage !== window.__lastStage) {
      window.__lastStage = s.stage;
      fetch("/clientlog", { method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ err: "[telemetry] " + snap }) }).catch(function () {});
    }
    if (isApprove) {
      $("detail").textContent = "";
      $("beacon").style.display = "none"; $("mock").style.display = "none";
      showBoard(s); return;
    }
    $("beacon").style.display = "block"; $("mock").style.display = "block";
    var secs = Math.round((Date.now() - t0) / 1000);
    var el = secs < 100 ? secs + "s"
           : Math.floor(secs / 60) + "m " + String(secs % 60).padStart(2, "0") + "s";
    $("detail").textContent =
      s.stage === "stills" && s.detail ? "sketching " + s.detail + " · " + el :
      s.stage === "film" && s.detail ? "rendering shot " + s.detail + " · " + el :
      s.stage === "critic" && s.detail ? s.detail + " · " + el :
      s.stage !== "done" ? el : "";
    if (s.stage === "done") {
      $("steps").style.display = "none"; $("detail").textContent = "";
      $("beacon").style.display = "none"; $("mock").style.display = "none";
      $("player").src = s.video;
      $("dl").href = s.video;
      $("title").textContent = s.title || "";
      $("meta").textContent = "cost $" + (+s.cost).toFixed(2);
      $("cap").textContent = s.caption || "";
      $("copycap").onclick = function () {
        navigator.clipboard.writeText(s.caption || "");
        this.textContent = "✓ Copied"; var b = this;
        setTimeout(function () { b.textContent = "Copy caption"; }, 1500);
      };
      $("cinema").style.display = "block";
      $("player").play().catch(function () {});
      loadVids();
      return;
    }
    if (s.stage === "error") {
      document.getElementById("panes").classList.remove("running");
      $("formErr").style.display = "block";
      $("formErr").textContent = s.error || "failed";
      $("go").disabled = false; $("log").disabled = false;
      return;
    }
    setTimeout(poll, 1200);
   } catch (e) {
    console.error("poll render:", e);
    fetch("/clientlog", { method: "POST", headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ err: "[poll] " + (e && e.stack || e) }) }).catch(function () {});
    setTimeout(poll, 2000);
   }
  }).catch(function (e) { console.error("poll fetch:", e); setTimeout(poll, 2000); });
}
</script>"""


import time as _time
PAGE = PAGE_TEMPLATE.replace("BUILD_STAMP", "b" + _time.strftime("%H%M"))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, code: int, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/trends":
            from showrunner.trends import fetch_trends
            period = "week" if "period=week" in self.path else "today"
            try:
                self._json(200, {"trends": fetch_trends(period)})
            except Exception as e:
                self._json(500, {"error": str(e)})
        elif path == "/status":
            with lock:
                self._json(200, dict(state))
        elif path == "/videos":
            uid = unquote(self.path.split("uid=", 1)[-1]) if "uid=" in self.path else ""
            runs = Path(__file__).parent / "runs"
            vids = []
            for d in (sorted(runs.iterdir(), reverse=True) if runs.exists() else []):
                f = d / "final.mp4"
                if not f.is_file() or f.stat().st_size < 500_000:
                    continue  # dry-run пустушки в бібліотеку не потрапляють
                own = d / "owner.txt"
                owner = own.read_text().strip() if own.is_file() else ""
                if owner and owner != uid:
                    continue  # чужий фільм — не показуємо
                def _read(name, key=None):
                    try:
                        raw = (d / name).read_text()
                        return json.loads(raw).get(key) if key else raw
                    except (OSError, ValueError):
                        return None
                poster = d / "board" / "shot_01.png"
                vids.append({"video": f"runs/{d.name}/final.mp4",
                             "poster": f"runs/{d.name}/board/shot_01.png" if poster.is_file() else "",
                             "title": _read("screenplay.json", "title") or "",
                             "cost": _read("run_report.json", "total_usd"),
                             "caption": (_read("caption.txt") or "")[:200],
                             "ts": d.name})
            self._json(200, {"videos": vids[:24]})
        elif path == "/video":
            # serves run artifacts (film + storyboard stills); runs/ only, no traversal
            types = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg"}
            p = Path(unquote(self.path.split("p=", 1)[-1].split("&", 1)[0])).resolve()
            runs = (Path(__file__).parent / "runs").resolve()
            if p.suffix in types and p.is_file() and p.is_relative_to(runs):
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", types[p.suffix])
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json(404, {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/approve":
            current_approve["ev"].set()
            with lock:
                if state["stage"] == "approve":
                    state["stage"] = "film"
            return self._json(200, {"ok": True})
        if self.path == "/drop":
            n = int(self.headers.get("Content-Length", 0))
            sid = json.loads(self.rfile.read(n) or b"{}").get("id")
            from showrunner import config as srconfig
            with lock:
                b = state.get("board")
                if state["stage"] != "approve" or not b:
                    return self._json(409, {"error": "not at the approval gate"})
                if len(b["shots"]) <= 1:
                    return self._json(400, {"error": "at least one shot must remain"})
                b["shots"] = [s for s in b["shots"] if s["id"] != sid]
                current_approve["edits"]["drop"].add(sid)
                if b.get("estimate"):
                    b["estimate"] = len(b["shots"]) * srconfig.COST_PER_CLIP_USD
                return self._json(200, {"board": b})
        if self.path == "/redraw":
            n = int(self.headers.get("Content-Length", 0))
            sid = json.loads(self.rfile.read(n) or b"{}").get("id")
            with lock:
                b = state.get("board")
                if state["stage"] != "approve" or not b:
                    return self._json(409, {"error": "not at the approval gate"})
                shot = next((s for s in b["shots"] if s["id"] == sid), None)
                size = b.get("size") or "720*1280"
            if not shot or not shot.get("img"):
                return self._json(404, {"error": "shot not found"})
            from showrunner.ledger import Ledger
            from showrunner.storyboard import generate_still
            out = Path(shot["img"])
            refs = sorted(out.parent.parent.glob("cast/*.png")) or None
            try:  # синхронно: 12-30с; фронт показує frost на комірці
                generate_still(shot["prompt"], size, out, Ledger(), refs=refs)
            except Exception as e:
                detail = getattr(getattr(e, "response", None), "text", "") or str(e)
                return self._json(502, {"error": detail[:200]})
            return self._json(200, {"ok": True, "img": shot["img"]})
        if self.path == "/clientlog":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            print(f"[client-js-error] {body.get('err', '')}", flush=True)
            return self._json(200, {"ok": True})
        if self.path == "/reset":
            # Start over: orphan whatever is running (its approve event dies
            # with it — it can never reach the paid FILM stage) and go idle.
            with lock:
                state["run_id"] += 1
                state.update(running=False, stage="idle", detail="", video=None,
                             cost=None, error=None, title="", caption="", log={},
                             board=None,
                             live={"script": None, "stills": [], "critic": [], "dailies": []})
            return self._json(200, {"ok": True})
        if self.path != "/run":
            return self._json(404, {"error": "not found"})
        with lock:
            if state["running"]:
                return self._json(409, {"error": "a run is already in progress"})
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        logline = str(body.get("logline", "")).strip()
        if not logline:
            return self._json(400, {"error": "logline required"})
        shots = max(3, min(15, int(body.get("shots", 12))))
        genre = str(body.get("genre", ""))[:40]
        cast = str(body.get("cast", ""))[:80]
        start_run(logline, bool(body.get("dry_run")), bool(body.get("vertical")),
                  shots_target=shots, genre=genre, cast=cast,
                  uid=str(body.get("uid", ""))[:64])
        self._json(200, {"ok": True})


if __name__ == "__main__":
    # прогрів тренд-кешу у фоні: перший відвідувач не чекає веб-пошук
    def _warm():
        try:
            from showrunner.trends import fetch_trends
            fetch_trends("today")
            fetch_trends("week")
        except Exception as e:
            print("trend warm-up failed:", e)
    threading.Thread(target=_warm, daemon=True).start()
    print(f"showrunner web → http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
