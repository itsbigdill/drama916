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
         "board": None, "run_id": 0, "input": None,
         "live": {"script": None, "stills": [], "critic": [], "dailies": []}}
lock = threading.Lock()
# one approve Event PER RUN: an abandoned run keeps waiting on its own dead
# event and can never sneak into the paid FILM stage.
current_approve = {"ev": threading.Event(), "edits": {"drop": set(), "order": [], "mods": {}}}


def start_run(logline: str, dry_run: bool, vertical: bool,
              shots_target: int = 12, genre: str = "", cast: str = "", uid: str = ""):
    with lock:
        state["run_id"] += 1
        my_run = state["run_id"]
    my_event = threading.Event()
    my_edits = {"drop": set(), "order": [], "mods": {}}
    current_approve["ev"] = my_event
    current_approve["edits"] = my_edits

    def approval():
        my_event.wait()
        return {"drop": sorted(my_edits["drop"]), "order": list(my_edits["order"]),
                "mods": dict(my_edits["mods"])}

    def cb(stage: str, detail: str):
        with lock:
            if state["run_id"] != my_run:
                return  # a Start over happened; this run is orphaned
            if stage.endswith("_live") or stage == "critic_tail":
                obj = json.loads(detail)
                if stage == "script_live":
                    state["live"]["script"] = obj
                elif stage == "board_live":
                    state["live"]["board"] = obj
                elif stage == "critic_tail":
                    state["live"]["ctail"] = obj
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

    cast_label = {"": "Auto", "realistic human characters": "Real",
                  "anthropomorphic fruit and vegetable characters": "Fruits",
                  "animal characters": "Animals",
                  "everyday objects brought to life as characters": "Objects"}.get(cast, cast or "Auto")
    with lock:
        state.update(running=True, stage="script", detail="", video=None,
                     cost=None, error=None, title="", caption="", log={}, board=None, uid=uid,
                     input={"logline": logline, "cast": cast_label, "secs": shots_target * 5},
                     live={"script": None, "stills": [], "critic": [], "dailies": []})
    threading.Thread(target=job, daemon=True).start()


PAGE_TEMPLATE = r"""<!doctype html><meta charset="utf-8"><title>drama916</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; font: 16px/1.5 -apple-system, system-ui;
         color: #1E1B39; background: #EFE9FF; display: flex; flex-direction: column;
         align-items: center; padding: 56px 18px; overflow-x: hidden; }
  @media (max-width: 680px) { body { padding: 26px 12px; } }
  body::before { content: ""; position: fixed; inset: 0; z-index: -1;
    background:
      radial-gradient(60% 45% at 8% 0%, rgba(168,85,247,.34), transparent 60%),
      radial-gradient(55% 45% at 100% 8%, rgba(232,121,249,.24), transparent 60%),
      radial-gradient(80% 55% at 50% 112%, rgba(124,58,237,.28), transparent 62%),
      linear-gradient(165deg, #ECE5FF 0%, #EEE6FF 45%, #F3ECFF 100%); }
  .mono { font-family: "JetBrains Mono", monospace; }
  .wordmark { font-family: "Unbounded", system-ui; font-weight: 800; font-size: 30px;
              letter-spacing: -.02em; margin-bottom: 28px; color: #241A47; }
  .dot { background: linear-gradient(92deg, #A855F7, #E879F9);
         -webkit-background-clip: text; background-clip: text; color: transparent;
         text-shadow: 0 0 22px rgba(168,85,247,.45); }
  #panes { width: 100%; max-width: 940px; display: flex; flex-direction: column; gap: 20px; align-items: center; }
  #formPane { max-width: 680px; width: 100%; display: flex; flex-direction: column;
              min-height: calc(100vh - 190px); }
  @media (max-width: 680px) {
    #formPane { min-height: calc(100vh - 130px); }
    #vstrip { margin: 0 -12px; padding: 6px 4px 36px; }
    #mq { margin: 0 -12px; padding: 4px 4px 12px; }
    #composer { margin: 0 -12px; width: calc(100% + 24px); }
    #vstrip .vcell { max-height: 440px; }
  }
  #runPane { align-self: stretch; }

  .bcell { cursor: grab; }
  .bcell:active { cursor: grabbing; }
  .bcell.dragging { opacity: .35; }
  .bcell.dragover { outline: 2px dashed #A855F7; outline-offset: 3px; }
  .glass { width: 100%; border-radius: 32px; padding: 36px 36px 38px; }
  @media (max-width: 680px) { .glass { padding: 24px 18px 26px; border-radius: 26px; } }
  .glass { 
           background: rgba(255,255,255,.58);
           border: 1px solid rgba(255,255,255,.65);
           backdrop-filter: blur(34px) saturate(1.5); -webkit-backdrop-filter: blur(34px) saturate(1.5);
           box-shadow: 0 30px 80px rgba(90,50,190,.20), 0 4px 14px rgba(60,30,120,.08),
                       inset 0 1px 0 rgba(255,255,255,.85); }
  textarea { width: 100%; border: 1px solid transparent; resize: none;
             background: rgba(255,255,255,.55);
             border-radius: 20px; padding: 18px 20px; font-size: 18px; line-height: 1.55;
             font-family: inherit; color: inherit; outline: none; min-height: 96px;
             box-shadow: inset 0 0 0 1px rgba(168,85,247,.14);
             transition: border-color .2s, box-shadow .25s; }
  textarea:focus { border-color: #C79BFF; box-shadow: 0 0 0 4px rgba(168,85,247,.16); }
  textarea::placeholder { color: #A99CC8; }
  textarea.invalid { border-color: #E5484D; box-shadow: 0 0 0 4px rgba(229,72,77,.14);
                     animation: shake .35s ease; }
  @keyframes shake { 25% { transform: translateX(-6px); } 75% { transform: translateX(6px); } }
  .row { display: flex; gap: 10px; align-items: stretch; margin-top: 22px; }
  /* trending: an auto-scrolling, hand-scrollable ribbon right above the composer */
  #mq { display: flex; gap: 8px; overflow-x: auto; margin: 0 -30px; padding: 4px 4px 12px;
        scrollbar-width: none; -ms-overflow-style: none; }
  #mq::-webkit-scrollbar { display: none; }
  .tpill { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 8px;
           background: rgba(255,255,255,.6); border: 1px solid rgba(255,255,255,.8);
           border-radius: 999px; padding: 9px 12px 9px 17px; cursor: pointer;
           font-size: 13px; font-weight: 600;
           box-shadow: 0 4px 14px rgba(90,50,190,.08); }
  .ttag { font-family: "JetBrains Mono", monospace; font-size: 9px; font-weight: 700;
          letter-spacing: .08em; text-transform: uppercase; color: #A78BDF;
          background: #F3E8FF; border-radius: 7px; padding: 3px 7px; }
  @media (max-width: 680px) {
    .tpill { padding: 8px 10px 8px 13px; font-size: 12.5px; }
  }
  .tpill { 
           color: #454363; transition: transform .1s, border-color .2s, background .2s; }
  .tpill:hover { border-color: #D8B4FE; background: #F3E8FF; color: #7C3AED; }
  .tpill:active { transform: scale(.95); }
  .tskel { width: 110px; height: 34px; border-radius: 999px; background: #F4F3FA;
           border: 1px solid #E7E5F3; animation: skel 1.1s ease-in-out infinite; }
  @keyframes skel { 50% { opacity: .45; } }
  textarea.flash { border-color: #B9AFFF; box-shadow: 0 0 0 4px rgba(108,92,231,.18); }
  /* composer: the ChatGPT-style card pinned to the bottom of the page —
     textarea on top, length/cast dropdowns + Action inside, one glass card */
  #mqwrap { margin-top: auto; }
  /* .glass pins width:100%, so negative margins alone would only shift the
     card left — widen it explicitly to reach the rail's right edge too */
  #composer { margin: 0 -30px; width: calc(100% + 60px); padding: 12px 14px 12px; border-radius: 28px; }
  #composer textarea { border: 0; background: transparent; box-shadow: none; border-radius: 0;
                       padding: 10px 10px 6px; min-height: 58px; max-height: 220px; font-size: 17px; }
  #composer textarea:focus { border: 0; box-shadow: none; }
  #composer textarea { scrollbar-width: none; }
  #composer textarea::-webkit-scrollbar { display: none; }
  #composer:focus-within { box-shadow: 0 30px 80px rgba(90,50,190,.24), 0 4px 14px rgba(60,30,120,.08),
                           0 0 0 4px rgba(168,85,247,.16), inset 0 1px 0 rgba(255,255,255,.85); }
  #composer:has(textarea.invalid) { box-shadow: 0 30px 80px rgba(90,50,190,.20),
                                    0 0 0 4px rgba(229,72,77,.16); animation: shake .35s ease; }
  #composer:has(textarea.flash) { box-shadow: 0 30px 80px rgba(90,50,190,.24),
                                  0 0 0 4px rgba(108,92,231,.2); }
  .crow { display: flex; align-items: center; gap: 8px; padding: 2px 2px 0; }
  .crow .go { flex: 0 0 auto; margin-left: auto; padding: 10px 20px 10px 13px;
              font-size: 12px; letter-spacing: .1em; }
  .crow .go::before { width: 24px; height: 24px; font-size: 13px; }
  /* recent generations: a horizontal 9:16 rail */
  #recentHead { display: flex; justify-content: space-between; align-items: center;
                margin: 4px -26px 12px; }
  .ghostlink { border: 0; background: transparent; cursor: pointer; padding: 4px 6px;
               font-family: "JetBrains Mono", monospace; font-size: 10px; font-weight: 700;
               letter-spacing: .14em; text-transform: uppercase; color: #B4B1CF;
               transition: color .15s; }
  .ghostlink:hover, .ghostlink.on { color: #7C3AED; }
  /* the rail bleeds past the pane so card shadows fade out instead of being
     clipped by the scrollport — a hard clip line reads as a wrapper box */
  /* the rail flex-grows: cards are exactly as tall as the free space between
     the header and the composer allows — no fixed sizes, no wasted space */
  #vstrip { flex: 1 1 0; min-height: 0; display: flex; gap: 16px; overflow-x: auto;
            margin: 0 -30px; padding: 6px 4px 44px;
            scrollbar-width: none; -ms-overflow-style: none; }
  #vstrip::-webkit-scrollbar { display: none; }
  #vstrip .vcell { flex: 0 0 auto; height: 100%; min-height: 236px; max-height: 680px;
                   aspect-ratio: 9/16; }
  #vstrip .vcell img, #vstrip .vcell video { width: 100%; height: 100%; }
  .ol { font-family: "JetBrains Mono", monospace; font-size: 10px; font-weight: 700;
        letter-spacing: .14em; text-transform: uppercase; color: #B4B1CF; padding-left: 3px; }
  .sel { position: relative; display: inline-flex; }
  .sel::after { content: "\2304"; position: absolute; right: 12px; top: 50%;
                transform: translateY(-58%); pointer-events: none; color: #8B88AC; font-size: 13px; }
  .sel select { appearance: none; -webkit-appearance: none; cursor: pointer; outline: none;
                border: 1px solid #E7E5F3; background: #F4F3FA; border-radius: 12px;
                padding: 8px 34px 8px 14px; color: #55536E;
                font-family: "JetBrains Mono", monospace; font-size: 12.5px; font-weight: 700;
                transition: border-color .18s, background .18s; }
  .sel select:hover { background: #F3E8FF; }
  .sel select:focus { border-color: #C79BFF; box-shadow: 0 0 0 4px rgba(168,85,247,.14); }
  /* an active (non-Auto) choice reads as "on", matching the chips */
  .sel select.set { color: #7C3AED; background: #F3E8FF; border-color: #D8B4FE; }
  .go { flex: 1; border: 0; border-radius: 999px; padding: 18px; cursor: pointer;
        display: inline-flex; align-items: center; justify-content: center; gap: 12px;
        background: linear-gradient(96deg, #E879F9 0%, #A855F7 48%, #7C3AED 100%);
        color: #FFFFFF; font-family: "Unbounded", system-ui; font-weight: 800;
        font-size: 15px; letter-spacing: .12em; text-transform: uppercase;
        box-shadow: 0 18px 40px rgba(168,85,247,.45), 0 2px 0 rgba(255,255,255,.25) inset;
        transition: transform .15s ease, filter .15s ease; }
  .go::before { content: "\2192"; display: inline-flex; align-items: center; justify-content: center;
        width: 30px; height: 30px; border-radius: 50%; background: rgba(255,255,255,.28);
        font-size: 16px; font-weight: 400; }
  .go:hover { transform: translateY(-2px); filter: brightness(1.07); }
  .go:active { transform: translateY(0); filter: brightness(.97); }
  .go:disabled { opacity: .45; box-shadow: none; transform: none; }

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
  #liveR:not(:empty) { margin-bottom: 14px; }
  #liveL:not(:empty) { margin-bottom: 14px; }
  .skrow { height: 15px; border-radius: 8px; margin: 13px 0;
           background: linear-gradient(100deg, #EFEBFB 40%, #F9F7FF 50%, #EFEBFB 60%);
           background-size: 220% 100%; animation: skshine 1.3s linear infinite; }
  .skrow.w60 { width: 60%; } .skrow.w80 { width: 80%; } .skrow.w45 { width: 45%; }
  @keyframes skshine { from { background-position: 130% 0; } to { background-position: -90% 0; } }
  #panelText:not(:empty) { background: rgba(255,255,255,.5); border: 1px solid rgba(255,255,255,.75);
    border-radius: 20px; padding: 20px 26px; margin-bottom: 14px; }
  #panelText .ptitle { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 16px;
    color: #26244A; margin-bottom: 10px; }
  #panelText .scene { font-size: 14px; }



  #runTitle { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 15px;
              color: #26244A; }
  #runsub { color: #A9A6C6; font-size: 12.5px; margin: 6px 0 2px; line-height: 1.45; }
  #runsub b { color: #8B88AC; font-weight: 600; }
  #runsub .rsopts { font-family: "JetBrains Mono", monospace; font-size: 11px; }

  #boardgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
               gap: 26px 22px; margin-top: 8px; }
  @media (max-width: 680px) {
    #boardgrid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 16px 12px; }
  }
  .bcell { position: relative; }
  .bcell img { width: 100%; border-radius: 16px; display: block;
               box-shadow: 0 14px 34px rgba(90,70,200,.20); }
  .bfall { border-radius: 16px; background: #FDF3F4; box-shadow: inset 0 0 0 1px #F5D5D8;
           display: flex; flex-direction: column; align-items: center; justify-content: center;
           gap: 8px; padding: 18px; text-align: center; }
  .bfall .bfi { font-size: 26px; }
  .bfall .bft { font-family: "JetBrains Mono", monospace; font-size: 11.5px; font-weight: 700;
                color: #B4232F; letter-spacing: .04em; }
  .bfbtn { border: 0; border-radius: 999px; padding: 9px 18px; cursor: pointer; margin-top: 4px;
           background: linear-gradient(96deg, #E879F9, #7C3AED); color: #FFF;
           font-family: "JetBrains Mono", monospace; font-size: 11.5px; font-weight: 700;
           box-shadow: 0 8px 20px rgba(168,85,247,.35); transition: transform .12s; }
  .bfbtn:hover { transform: translateY(-1px); }
  #boardgrid.v916 .bfall { aspect-ratio: 9/16; }
  #boardgrid.v169 .bfall { aspect-ratio: 16/9; }
  .bcell .bp { font-size: 12.5px; color: #9490B4; margin-top: 5px; line-height: 1.5; }
  .bcell .bp b { color: #6B6890; font-weight: 600; }
  .bcell .bn { position: absolute; top: 10px; left: 10px; background: rgba(255,255,255,.94);
               color: #5646D6; font-family: "JetBrains Mono", monospace; font-size: 11px;
               font-weight: 700; border-radius: 9px; padding: 3px 9px;
               box-shadow: 0 2px 8px rgba(34,33,58,.18); }
  .bcell .bs { font-size: 16px; color: #33314E; font-weight: 600; margin-top: 14px; line-height: 1.45; }
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
  .lthumbs { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; }
  .lthumbs img { width: 128px; height: 204px; object-fit: cover; border-radius: 14px;
                 box-shadow: 0 6px 14px rgba(90,70,200,.16); animation: pop .3s ease; }
  @keyframes pop { 0% { transform: scale(.6); opacity: 0; } }
  #feed { margin-top: 10px; display: none; }
  .fblk { border-top: 1px solid #EFEDF9; padding: 6px 0; }
  .fblk summary { list-style: none; cursor: pointer; display: flex; gap: 12px;
                  align-items: baseline; padding: 12px 4px; border-radius: 12px;
                  transition: background .15s; }
  .fblk summary:hover { background: #FAF9FE; }
  .fblk summary::-webkit-details-marker { display: none; }
  .fblk summary::after { content: "\203A"; margin-left: auto; color: #C6C3DE;
                         font-size: 18px; transition: transform .2s; }
  .fblk[open] summary::after { transform: rotate(90deg); }
  .fblk .fl { font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700;
              letter-spacing: .12em; color: #6C5CE7; flex: 0 0 64px; }
  .fblk .fv { font-size: 14.5px; color: #33314E; }
  .fblk .fv b { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 13.5px; }
  .fbody { padding: 4px 4px 16px 40px; }
  .scene { font-size: 13.5px; color: #55536E; padding: 10px 0; border-top: 1px dashed #EFEDF8;
           line-height: 1.6; }
  .scene:first-child { border-top: 0; }
  .scene .sn { font-family: "JetBrains Mono", monospace; font-size: 10.5px; font-weight: 700;
               color: #A08CFF; margin-right: 7px; }
  .scene .sset { font-weight: 600; color: #454363; }
  .scene .ssub { color: #8B88AC; font-style: italic; }
  .ffix { color: #6C5CE7; }
  .gwrap { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
           gap: 14px; margin-top: 14px; }
  .gcell { position: relative; border-radius: 14px; overflow: hidden; }
  .gcell img { width: 100%; height: 240px; object-fit: cover; display: block;
               filter: saturate(.35) brightness(1.12) blur(2px); opacity: .68; }
  .gcell::after { content: ""; position: absolute; inset: 0;
    background: linear-gradient(115deg, transparent 35%, rgba(255,255,255,.75) 50%, transparent 65%);
    background-size: 240% 100%; animation: frost 2.4s linear infinite; }
  .gcell:nth-child(3n+2)::after { animation-delay: .5s; }
  .gcell:nth-child(3n)::after { animation-delay: 1s; }
  @keyframes frost { from { background-position: 130% 0; } to { background-position: -130% 0; } }
  .fnote { font-family: "JetBrains Mono", monospace; font-size: 11.5px; color: #8B88AC;
           padding: 7px 0; line-height: 1.55; }
  .fnote:first-child { color: #6B6890; }
  .fthumbs { display: flex; gap: 7px; flex-wrap: wrap; padding-top: 4px; }
  .fthumbs img { width: 52px; height: 74px; object-fit: cover; border-radius: 9px;
                 box-shadow: 0 6px 14px rgba(90,70,200,.16); }

  /* premiere: big vertical frame, title/caption/actions in a side panel
     (stacked below the video on narrow screens) */
  #cinema { display: none; margin-top: 4px; }
  #ttwrap { display: flex; gap: 36px; justify-content: center; align-items: flex-start; }
  #ttframe { flex: 0 0 auto; height: min(calc(100vh - 245px), 820px); min-height: 460px;
             aspect-ratio: 9/16; max-width: 100%;
             border-radius: 26px; overflow: hidden;
             background: #0E0D18; box-shadow: 0 34px 90px rgba(34,33,58,.38); }
  #ttframe video { width: 100%; height: 100%; object-fit: cover; display: block; background: #0E0D18; }
  #ttinfo { flex: 0 1 330px; min-width: 0; padding-top: 12px; }
  #title { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 19px;
           color: #33314E; margin-bottom: 10px; }
  #cap { font-size: 13.5px; line-height: 1.65; color: #55536E;
         white-space: pre-wrap; cursor: pointer; }
  #cap:empty { display: none; }
  #meta { font-family: "JetBrains Mono", monospace; font-size: 11.5px;
          color: #8B88AC; margin-top: 12px; }
  #ttacts { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
  .tact { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 16px;
          border: 0; border-radius: 20px; cursor: pointer; text-decoration: none;
          font: 600 13px -apple-system, system-ui; color: #454363;
          background: rgba(255,255,255,.72);
          box-shadow: 0 6px 18px rgba(34,33,58,.10), inset 0 0 0 1px rgba(122,92,255,.14);
          transition: transform .12s, box-shadow .15s; }
  .tact:hover { transform: translateY(-1px);
                box-shadow: 0 10px 24px rgba(34,33,58,.16), inset 0 0 0 1px rgba(122,92,255,.28); }
  .tact svg { width: 15px; height: 15px; flex: 0 0 auto; }
  @media (max-width: 760px) {
    #ttwrap { flex-direction: column; align-items: center; gap: 18px; }
    #ttframe { height: min(64vh, 620px); }
    #ttinfo { flex: 0 0 auto; width: min(100%, 420px); padding-top: 0; text-align: center; }
    #ttacts { justify-content: center; }
  }
  .ghost { border: 0; background: transparent; cursor: pointer; padding: 0 8px;
           color: #8B88AC; font: 700 13px -apple-system, system-ui; }

  #err { display: none; margin-top: 16px; font-size: 14px; color: #E5484D; }
  .bx { position: absolute; top: 10px; right: 10px; display: flex; gap: 7px; z-index: 2;
        opacity: 1; transition: opacity .2s; }
  .bbtn { width: 32px; height: 32px; border: 0; border-radius: 50%; cursor: pointer;
          background: rgba(255,255,255,.95); color: #454363; font-size: 15px; line-height: 1;
          box-shadow: 0 4px 14px rgba(34,33,58,.24); transition: transform .12s, background .15s; }
  .bbtn:hover { transform: scale(1.12); background: #FFF; }
  .bbtn.dr:hover { color: #E5484D; }
  .bbtn:disabled { opacity: .35; transform: none; }
  @media (hover: hover) { .bx { opacity: 0; } .bcell:hover .bx { opacity: 1; } }
  .bimg { position: relative; }
  .rnote { position: absolute; left: 8px; right: 8px; bottom: 8px; z-index: 3;
           display: none; gap: 6px; }
  .rnote.open { display: flex; }
  .rnote input { flex: 1; min-width: 0; border: 0; border-radius: 11px; padding: 9px 12px;
                 font: 500 12.5px -apple-system, system-ui; color: #33314E;
                 background: rgba(255,255,255,.96); outline: none;
                 box-shadow: 0 6px 18px rgba(34,33,58,.28), inset 0 0 0 1px #E7E5F3; }
  .rnote input::placeholder { color: #A9A6C6; }
  .rgo { flex: 0 0 auto; width: 34px; border: 0; border-radius: 11px; cursor: pointer;
         background: linear-gradient(180deg, #7A5CFF, #5B45E0); color: #FFF; font-size: 15px;
         box-shadow: 0 6px 16px rgba(108,92,231,.4); }
  .bscene { font-size: 13px; line-height: 1.55; color: #9490B4; margin-top: 7px; }
  .bscene b { color: #6B6890; font-weight: 600; }
  .bcell.rf img { filter: saturate(.35) brightness(1.12) blur(2px); opacity: .68; }
  .bcell.rf::after { content: ""; position: absolute; inset: 0; border-radius: inherit;
    background: linear-gradient(115deg, transparent 35%, rgba(255,255,255,.75) 50%, transparent 65%);
    background-size: 240% 100%; animation: frost 2.4s linear infinite; }
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

  /* —— Studio: full-screen production workspace —— */
  #studio { display: none; }
  body.studio { overflow: hidden; }
  body.studio .wordmark, body.studio #panes, body.studio .foot { display: none; }
  body.studio #studio { display: flex; flex-direction: column; position: fixed; inset: 0; z-index: 5; }
  #stTop { display: flex; align-items: center; gap: 16px; padding: 11px 22px; flex: 0 0 auto;
           background: rgba(255,255,255,.62); border-bottom: 1px solid rgba(255,255,255,.8);
           backdrop-filter: blur(30px) saturate(1.4); -webkit-backdrop-filter: blur(30px) saturate(1.4); }
  .stmark { font-family: "Unbounded", system-ui; font-weight: 800; font-size: 15px; color: #241A47; }
  #stTop #runsub { flex: 1; min-width: 0; margin: 0; overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; }
  #stBody { flex: 1; display: flex; overflow: hidden; }
  #stCanvas { flex: 1; overflow-y: auto; padding: 26px 40px 40px; }
  #stInner { max-width: 1100px; margin: 0 auto; }
  /* breadcrumb stage nav: done/live are clickable pages, future is muted */
  #crumbs { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-bottom: 22px; }
  .crumb { border: 0; cursor: pointer; border-radius: 999px; padding: 8px 16px;
           font-family: "JetBrains Mono", monospace; font-size: 12px; font-weight: 700;
           letter-spacing: .04em; background: #F3E8FF; color: #7C3AED;
           transition: background .18s, transform .12s; }
  .crumb:hover { transform: translateY(-1px); }
  .crumb.live { background: linear-gradient(96deg, #E879F9, #7C3AED); color: #FFF;
                box-shadow: 0 8px 22px rgba(168,85,247,.35); }
  .crumb.live .cdot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
                      background: #FFF; margin-right: 7px; animation: pulse 1.2s ease-in-out infinite; }
  .crumb.viewing { background: #FFFFFF; box-shadow: inset 0 0 0 2px #C084FC; }
  .crumb.future { background: transparent; color: #B9B7D2; cursor: default; }
  .crumb.future:hover { transform: none; }
  .csep { color: #C6C3DE; font-size: 12px; }
  #stStatus { font-family: "JetBrains Mono", monospace; font-size: 11.5px;
              color: #A9A6C6; margin: -8px 0 18px 4px; min-height: 15px; }
  #stBar { display: none; align-items: center; gap: 14px; padding: 12px 22px; flex: 0 0 auto;
           background: rgba(255,255,255,.7); border-top: 1px solid rgba(255,255,255,.8);
           backdrop-filter: blur(30px) saturate(1.4); -webkit-backdrop-filter: blur(30px) saturate(1.4); }
  #stBar.show { display: flex; }
  #barInfo { font-family: "JetBrains Mono", monospace; font-size: 12px; color: #8B88AC; }
  .barbtns { margin-left: auto; display: flex; gap: 10px; align-items: center; }
  #stBar .go { flex: 0 0 auto; padding: 12px 30px; font-size: 13px; }
  #stBar .go::before { width: 24px; height: 24px; font-size: 13px; }
  .gray2 { border: 0; border-radius: 999px; padding: 0 30px; min-height: 48px; cursor: pointer;
           display: inline-flex; align-items: center; justify-content: center;
           background: rgba(120,110,160,.14); color: #6B6890;
           font-family: "Unbounded", system-ui; font-weight: 800; font-size: 13px;
           letter-spacing: .12em; text-transform: uppercase; transition: background .18s; }
  .gray2:hover { background: rgba(120,110,160,.24); }
  @media (max-width: 680px) {
    #stTop { gap: 10px; padding: 10px 14px; }
    #stTop #runsub { display: none !important; }
    #stTop #runTitle { font-size: 13px; white-space: nowrap; overflow: hidden;
                       text-overflow: ellipsis; max-width: 58vw; }
    #stCanvas { padding: 16px 14px; }
    .crumb { padding: 7px 12px; font-size: 11px; }
    #stBar { padding: 10px 14px; }
    #barInfo { display: none; }
    .barbtns { margin-left: 0; width: 100%; }
    .barbtns .go, .barbtns .gray2 { flex: 1; padding: 0 12px; }
    #stBar .go { padding: 14px 12px; }
  }
  .tcount { margin-left: 6px; color: #B4B1CF; font-size: 11px; }
  .tabempty { color: #A9A6C6; font-size: 14px; padding: 26px 4px; text-align: center; line-height: 1.5; }
  #dgrid { display: flex; flex-direction: column; gap: 8px; }
  .dcell { display: flex; align-items: center; gap: 10px; padding: 13px 15px; border-radius: 14px;
           background: rgba(255,255,255,.5); border: 1px solid #EDE9F9; cursor: pointer;
           transition: border-color .18s, background .18s; }
  .dcell:hover { border-color: #D8B4FE; background: #FAF7FF; }
  .dtxt { flex: 1; min-width: 0; font-size: 14px; color: #33314E;
          overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ddel { border: 0; background: transparent; cursor: pointer; color: #B4B1CF; font-size: 13px; flex: 0 0 auto; }
  .ddel:hover { color: #E5484D; }
</style>
<body>
<div class="wordmark">drama<span class="dot">916</span></div>

<div id="panes">
  <div id="formPane">

  <div id="recentHead">
    <span class="ol">Recent generations</span>
    <button id="draftsBtn" class="ghostlink">Drafts<span id="dcount" class="tcount"></span></button>
  </div>
  <div id="vstrip"></div>
  <div id="vempty" class="tabempty" style="display:none">No films yet. Your finished films land here.</div>
  <div id="dpanel" style="display:none">
    <div id="dgrid"></div>
    <div id="dempty" class="tabempty">Nothing saved yet. Start a line — it's kept here automatically.</div>
  </div>

  <div id="mqwrap">
    <div id="mq"></div>
    <div id="composer" class="glass">
      <textarea id="log" placeholder="One line. A whole film."></textarea>
      <div class="crow">
        <span class="sel"><select id="selLen" title="Length"><option value="3">15s</option><option value="6" selected>30s</option><option value="9">45s</option><option value="12">60s</option></select></span>
        <span class="sel"><select id="selCast" title="Cast"><option value="">Auto</option><option value="realistic human characters">Real</option><option value="anthropomorphic fruit and vegetable characters">Fruits</option><option value="animal characters">Animals</option><option value="everyday objects brought to life as characters">Objects</option></select></span>
        <button id="go" class="go">Action</button>
      </div>
      <div id="formErr" style="display:none;margin:8px 10px 4px;font-size:14px;color:#E5484D"></div>
    </div>
  </div>
  </div><!-- /formPane -->

</div><!-- /panes -->

<div id="studio">
  <div id="stTop">
    <span class="stmark">drama<span class="dot">916</span></span>
    <span id="runTitle">Production</span>
    <span id="runsub"></span>
    <button class="ghost" onclick="startOver()" title="close">✕</button>
  </div>

  <div id="stBody">
    <div id="stCanvas"><div id="stInner">
      <div id="crumbs"></div>
      <div id="stStatus"></div>
      <div id="panelText"></div>
      <div id="liveL"></div>
      <div id="liveR"></div>
      <div id="board" style="display:none"><div id="shotlist"></div></div>
      <div id="cinema">
        <div id="ttwrap">
          <div id="ttframe">
            <video id="player" controls playsinline></video>
          </div>
          <div id="ttinfo">
            <div id="title"></div>
            <div id="cap" title="tap to copy"></div>
            <div id="meta"></div>
            <div id="ttacts">
              <a id="dl" class="tact" download="drama916.mp4"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="3" x2="12" y2="15"/></svg><span>Download</span></a>
              <button id="copycap" class="tact"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span id="caplbl">Copy caption</span></button>
              <button id="ttshare" class="tact" style="display:none"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg><span>Share</span></button>
            </div>
          </div>
        </div>
      </div>
      <div id="dbg" style="display:none;margin-top:10px;font:10px/1.4 monospace;color:#C6C3DE"></div>
      <div id="err"></div>
    </div></div>
  </div>

  <div id="stBar">
    <span id="barInfo"></span>
    <span class="barbtns" id="barApprove" style="display:none">
      <button class="gray2" onclick="startOver()">Start over</button>
      <button id="film" class="go">Film it</button>
    </span>
    <span class="barbtns" id="barDone" style="display:none">
      <button class="gray2" onclick="startOver()">Start over</button>
    </span>
  </div>
</div>

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
var vidsN = 0;
function loadVids() {
  fetch("/videos?uid=" + encodeURIComponent(uid)).then(function (r) { return r.json(); }).then(function (d) {
    var vids = d.videos || [];
    vidsN = vids.length;
    if ($("dpanel").style.display === "none")
      $("vempty").style.display = vidsN ? "none" : "block";
    $("vstrip").innerHTML = vids.map(function (v, i) {
      return '<div class="vcell" data-i="' + i + '">' +
             (v.poster ? '<img src="/video?p=' + encodeURIComponent(v.poster) + '" loading="lazy">'
                       : '<img alt="">') +
             '<span class="vplay"></span>' +
             '<div class="vmeta"><div class="vt">' + String(v.title || "Untitled").replace(/</g, "&lt;") + '</div>' +
             '<div class="vc">' + (v.cost != null ? "$" + (+v.cost).toFixed(2) : "") + '</div></div></div>';
    }).join("");
    $("vstrip").querySelectorAll(".vcell").forEach(function (c) {
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

// Drafts live behind a toggle next to Recent generations
function showDrafts(on) {
  $("dpanel").style.display = on ? "block" : "none";
  $("vstrip").style.display = on ? "none" : "flex";
  $("vempty").style.display = (!on && !vidsN) ? "block" : "none";
  $("draftsBtn").classList.toggle("on", on);
  if (on) renderDrafts();
}
$("draftsBtn").onclick = function () {
  upsertDraft();  // keep whatever's currently typed
  showDrafts($("dpanel").style.display === "none");
};

// Drafts: a list of your saved loglines (kept automatically as you write/run)
function getDrafts() { try { return JSON.parse(localStorage.getItem("sr_drafts") || "[]"); } catch (e) { return []; } }
function setDrafts(a) { try { localStorage.setItem("sr_drafts", JSON.stringify(a.slice(0, 12))); } catch (e) {} }
function upsertDraft() {
  var line = $("log").value.trim();
  if (line.length < 4) return;
  var a = getDrafts().filter(function (x) { return x.logline !== line; });
  a.unshift({ logline: line, len: opts.len, cast: opts.cast });
  setDrafts(a);
  $("dcount").textContent = a.length;
}
function renderDrafts() {
  var a = getDrafts();
  $("dcount").textContent = a.length ? a.length : "";
  $("dempty").style.display = a.length ? "none" : "block";
  $("dgrid").innerHTML = a.map(function (x, i) {
    return '<div class="dcell" data-i="' + i + '"><span class="dtxt">' + esc2(x.logline) + '</span>' +
           '<button class="ddel" data-i="' + i + '" title="delete">✕</button></div>';
  }).join("");
  $("dgrid").querySelectorAll(".dcell").forEach(function (c) {
    c.onclick = function (e) {
      if (e.target.classList.contains("ddel")) return;
      var x = getDrafts()[+c.dataset.i]; if (!x) return;
      $("log").value = x.logline; fitLog();
      if (x.len) { opts.len = x.len; $("selLen").value = x.len; }
      if (x.cast != null) { opts.cast = x.cast; $("selCast").value = x.cast; $("selCast").classList.toggle("set", !!x.cast); }
      saveDraft();
      showDrafts(false);
      $("log").focus();
    };
  });
  $("dgrid").querySelectorAll(".ddel").forEach(function (b) {
    b.onclick = function (e) {
      e.stopPropagation();
      var a2 = getDrafts(); a2.splice(+b.dataset.i, 1); setDrafts(a2); renderDrafts();
    };
  });
}
renderDrafts();

function enterRun() {
  document.body.classList.add("studio");
  if (!t0) t0 = Date.now();
  poll();
}
// auto-draft: the typed logline + options survive a refresh
function saveDraft() {
  try {
    localStorage.setItem("sr_draft", JSON.stringify(
      { logline: $("log").value, len: opts.len, cast: opts.cast }));
  } catch (e) {}
}
function restoreDraft() {
  try {
    var d = JSON.parse(localStorage.getItem("sr_draft") || "null");
    if (!d) return;
    if (d.logline) { $("log").value = d.logline; fitLog(); }
    if (d.len) { opts.len = d.len; $("selLen").value = d.len; }
    if (d.cast) { opts.cast = d.cast; $("selCast").value = d.cast; $("selCast").classList.toggle("set", !!d.cast); }
  } catch (e) {}
}
// рефреш не втрачає роботу: активний ран повертаємось у нього; інакше — чернетка
window.addEventListener("load", function () {
  fetch("/status").then(function (r) { return r.json(); }).then(function (s) {
    if (s.stage && s.stage !== "idle") enterRun();
    else restoreDraft();
  }).catch(restoreDraft);
});
// drama916: always vertical 9:16, always drama. Cast optional (empty by default
// so a named character renders as itself instead of being humanized).
var opts = { fmt: "916", len: "6", genre: "", cast: "" };
$("selLen").onchange = function () { opts.len = this.value; saveDraft(); };
$("selCast").onchange = function () {
  opts.cast = this.value;
  this.classList.toggle("set", !!this.value);
  saveDraft();
};
// the composer grows with the text, like a chat input
function fitLog() {
  var f = $("log");
  f.style.height = "auto";
  f.style.height = Math.min(f.scrollHeight, 220) + "px";
}
$("log").addEventListener("input", function () { fitLog(); saveDraft(); });
$("log").addEventListener("keydown", function (e) {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("go").click(); }
});

// тренд-скаут: today + week упереміш в одній стрічці над композером;
// їде сама, зупиняється під курсором/пальцем, гортається руками
function renderMarquee(list) {
  var mq = $("mq");
  if (!list.length) { mq.innerHTML = ""; return; }
  var html = list.map(function (tr, i) {
    return '<button class="tpill" data-i="' + i + '" title="' +
           (tr.why || "").replace(/"/g, "&quot;") + '">' + esc2(tr.topic) +
           '<span class="ttag">' + (tr.period === "week" ? "this week" : "today") + '</span></button>';
  }).join("");
  mq.innerHTML = html;
  // duplicate only when the ribbon overflows — that's what makes the loop seamless
  if (mq.scrollWidth > mq.clientWidth + 30) { mq.innerHTML = html + html; mq.dataset.loop = "1"; }
  else mq.dataset.loop = "";
  mq.querySelectorAll(".tpill").forEach(function (c) {
    c.onclick = function () {
      var tr = list[+c.dataset.i];
      var f = $("log");
      f.value = tr.logline; fitLog(); saveDraft();
      f.classList.add("flash");
      setTimeout(function () { f.classList.remove("flash"); }, 900);
    };
  });
}
function loadTrends() {
  $("mq").innerHTML = '<span class="tskel"></span><span class="tskel"></span><span class="tskel"></span><span class="tskel"></span><span class="tskel"></span>';
  Promise.all(["today", "week"].map(function (p) {
    return fetch("/trends?period=" + p).then(function (r) { return r.json(); })
      .then(function (d) { return (d.trends || []).map(function (x) { x.period = p; return x; }); })
      .catch(function () { return []; });
  })).then(function (rr) {
    var mixed = [];  // interleave so both periods surface up front
    for (var i = 0; i < Math.max(rr[0].length, rr[1].length); i++) {
      if (rr[0][i]) mixed.push(rr[0][i]);
      if (rr[1][i]) mixed.push(rr[1][i]);
    }
    renderMarquee(mixed);
  });
}
loadTrends();
var mqPause = false, mqResumeT = null;
$("mq").addEventListener("pointerenter", function () { mqPause = true; });
$("mq").addEventListener("pointerleave", function () { mqPause = false; });
$("mq").addEventListener("touchstart", function () {
  mqPause = true; clearTimeout(mqResumeT);
}, { passive: true });
$("mq").addEventListener("touchend", function () {
  clearTimeout(mqResumeT);
  mqResumeT = setTimeout(function () { mqPause = false; }, 1800);
}, { passive: true });
// scrollLeft rounds to whole pixels, so a fractional step must accumulate
// in its own float — otherwise +0.45 rounds back to 0 and the ribbon stalls
var mqX = 0;
$("mq").addEventListener("scroll", function () { if (mqPause) mqX = this.scrollLeft; });
(function mqTick() {
  var mq = $("mq");
  if (mq && mq.dataset.loop && !mqPause) {
    var half = mq.scrollWidth / 2;
    mqX += 0.45;
    if (mqX >= half) mqX -= half;
    mq.scrollLeft = mqX;
  }
  requestAnimationFrame(mqTick);
})();

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
  upsertDraft();  // keep this idea in Drafts
  $("go").disabled = true; $("log").disabled = true; t0 = Date.now();
  fetch("/run", { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ logline: logline, vertical: true, uid: uid,
                                         shots: +opts.len, genre: opts.genre, cast: opts.cast }) })
    .then(function (r) {
      if (!r.ok) {
        return r.json().then(function (e) {
          $("go").disabled = false; $("log").disabled = false;
          $("err").style.display = "block";
          $("err").textContent = e.error || "could not start";
        });
      }
      enterRun();
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
// ————— breadcrumb stages: each pipeline step is a page in the canvas —————
var CRUMBS = ["Script", "Board", "Critic", "Storyboard", "Film"];
var userView = null;  // null = follow the live stage

function liveIdxOf(stage) {
  if (stage === "approve") return 3;
  // усе після approve — один фінальний етап Film: рендер, дейліз, голос,
  // монтаж і сама прем'єра
  if (["film", "dailies", "voice", "cut", "done"].indexOf(stage) >= 0) return 4;
  var i = ORDER.indexOf(stage);
  return i < 0 ? 0 : (i === 3 ? 3 : i);
}

function renderCrumbs(s) {
  var li = liveIdxOf(s.stage);
  var view = userView === null ? li : userView;
  var h = "";
  for (var i = 0; i < CRUMBS.length; i++) {
    if (i) h += '<span class="csep">\u203A</span>';
    var cls = i === li ? "crumb live" : (i < li ? "crumb" : "crumb future");
    if (i === view && i !== li) cls += " viewing";
    h += '<button class="' + cls + '" data-i="' + i + '">' +
         (i === li && s.stage !== "done" ? '<span class="cdot"></span>' : "") + CRUMBS[i] + '</button>';
  }
  $("crumbs").innerHTML = h;
  $("crumbs").querySelectorAll(".crumb").forEach(function (b) {
    var i = +b.dataset.i;
    if (i > li) return;                    // майбутнє — некликабельне
    b.onclick = function () { userView = (i === li) ? null : i; poll0(); };
  });
}

function esc2(x) { return String(x == null ? "" : x).replace(/</g, "&lt;"); }

function panelScript(s) {
  var sc = (s.log && s.log.script) || null;
  if (!sc) return "";
  var scenes = Array.isArray(sc.scenes) ? sc.scenes : [];
  return '<div class="ptitle">\u201C' + esc2(sc.title) + '\u201D \u00B7 ' + scenes.length + ' scenes</div>' +
    scenes.map(function (x) {
      return '<div class="scene"><span class="sn">' + esc2(x.id) + '</span>' +
             '<span class="sset">' + esc2(x.setting) + '</span> \u2014 ' + esc2(x.action) +
             (x.subtitle ? ' <span class="ssub">\u201C' + esc2(x.subtitle) + '\u201D</span>' : "") + '</div>';
    }).join("");
}

// pull every completed "key":"value" out of a PARTIAL json stream — this is
// what turns a raw model stream into rows appearing one by one
function jvals(tail, key) {
  var out = [], re = new RegExp('"' + key + '"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"', "g"), m;
  while ((m = re.exec(tail || ""))) out.push(m[1].replace(/\\"/g, '"'));
  return out;
}
function skel(n) {
  var w = ["w80", "w60", "w45"], h = "";
  for (var i = 0; i < n; i++) h += '<div class="skrow ' + w[i % 3] + '"></div>';
  return h;
}

function panelBoardLive(s) {
  var tail = (s.live && s.live.board && s.live.board.tail) || "";
  var acts = jvals(tail, "action"), subs = jvals(tail, "subtitle");
  var h = '<div class="ptitle">planning shots\u2026</div>';
  for (var i = 0; i < acts.length; i++) {
    h += '<div class="scene"><span class="sn">' + String(i + 1).padStart(2, "0") + '</span>' +
         esc2(acts[i]) + (subs[i] ? ' <span class="ssub">\u201C' + esc2(subs[i]) + '\u201D</span>' : "") + '</div>';
  }
  return h + skel(acts.length ? 2 : 3);
}

function panelBoard(s) {
  var b = (s.log && s.log.board) || null;
  if (!b) return "";
  var shots = Array.isArray(b.shots) ? b.shots : [];
  return '<div class="ptitle">' + shots.length + ' shots planned</div>' +
    shots.map(function (sh) {
      return '<div class="scene"><span class="sn">' + String(sh.id).padStart(2, "0") + '</span>' +
             esc2(sh.prompt) + (sh.subtitle ? ' <span class="ssub">\u201C' + esc2(sh.subtitle) + '\u201D</span>' : "") + '</div>';
    }).join("");
}

function panelCriticLive(s) {
  var L = s.live || {};
  var tail = (L.ctail && L.ctail.tail) || "";
  var rnd = (L.ctail && L.ctail.round) || 1;
  var probs = jvals(tail, "problem"), fixes = jvals(tail, "fix");
  var score = /"score"\s*:\s*(\d+)/.exec(tail);
  var h = '<div class="ptitle">critic \u00B7 round ' + rnd +
          (score ? ' \u00B7 ' + score[1] + "/10" : "") + '\u2026</div>';
  (L.critic || []).forEach(function (r) {
    h += '<div class="lline"><b>R' + r.round + ' \u00B7 ' + (r.score != null ? r.score + "/10" : "\u2014") + '</b>' +
         (r.fixes && r.fixes.length ? " \u2014 " + esc2(r.fixes.join("; ")) : " \u2014 approved") + '</div>';
  });
  for (var i = 0; i < probs.length; i++) {
    h += '<div class="fnote">\u2717 ' + esc2(probs[i]) +
         (fixes[i] ? ' <span class="ffix">\u2192 ' + esc2(fixes[i]) + '</span>' : "") + '</div>';
  }
  return h + skel(probs.length ? 1 : 2);
}

function panelCritic(s) {
  var c = (s.log && s.log.critic) || null;
  var L = s.live || {};
  if (!c && L.critic && L.critic.length) {
    return '<div class="ptitle">critic \u00B7 reviewing\u2026</div>' + L.critic.map(function (r) {
      return '<div class="lline"><b>R' + r.round + ' \u00B7 ' + (r.score != null ? r.score + "/10" : "\u2014") + '</b>' +
             (r.fixes && r.fixes.length ? " \u2014 " + esc2(r.fixes.join("; ")) : " \u2014 approved") + '</div>';
    }).join("");
  }
  if (!c) return "";
  var head = c.rewrote
      ? "draft " + (c.score != null ? c.score + "/10" : "rejected") + " \u2192 rewrote the board" +
        (c.shots ? " \u00B7 " + c.shots + " shots" : "")
      : (c.score != null ? "score " + c.score + "/10" : "approved") +
        (c.shots ? " \u00B7 " + c.shots + " shots final" : "");
  return '<div class="ptitle">' + head + '</div>' +
    (c.verdict ? '<div class="fnote">' + esc2(c.verdict) + '</div>' : "") +
    (c.notes || []).map(function (n) {
      if (typeof n === "string") return '<div class="fnote">\u2717 ' + esc2(n) + '</div>';
      return '<div class="fnote">\u2717 ' + esc2(n.problem) +
             (n.fix ? ' <span class="ffix">\u2192 ' + esc2(n.fix) + '</span>' : "") + '</div>';
    }).join("");
}

function renderStage(s) {
  var li = liveIdxOf(s.stage);
  var view = userView === null ? li : userView;
  var atLive = view === li;
  // reset all zones; each branch turns on what it owns
  $("panelText").innerHTML = "";
  $("liveL").innerHTML = "";
  $("board").style.display = "none";
  $("cinema").style.display = "none";
  if (view !== 4 && view !== 3 && $("liveR").dataset.mode) { $("liveR").dataset.mode = ""; $("liveR").innerHTML = ""; }

  if (view === 0) {  // Script
    var L = s.live || {};
    if (atLive && s.stage === "script" && L.script && L.script.tail) {
      $("liveL").innerHTML = '<div class="llab">writer \u00B7 ' + (L.script.kind === "thinking" ? "thinking" : "writing") + '</div>' +
        '<div class="lcon' + (L.script.kind === "thinking" ? " dim" : "") + '">' + esc2(L.script.tail) + '</div>';
    } else {
      $("panelText").innerHTML = panelScript(s);
    }
  } else if (view === 1) {  // Board
    $("panelText").innerHTML = (atLive && s.stage === "board") ? panelBoardLive(s) : panelBoard(s);
  } else if (view === 2) {  // Critic
    $("panelText").innerHTML = (atLive && s.stage === "critic") ? panelCriticLive(s) : panelCritic(s);
  } else if (view === 3) {  // Storyboard
    if (s.stage === "stills") {
      var L3 = s.live || {};
      if (L3.stills && L3.stills.length)
        syncThumbs($("liveR"), "stills", "storyboard", "lthumbs", false,
                   L3.stills.map(function (st) { return st.img; }));
    } else if (s.board && (s.board.shots || []).length) {
      // the stills preview strip must not linger above the real board
      if ($("liveR").dataset.mode) { $("liveR").dataset.mode = ""; $("liveR").innerHTML = ""; }
      var ro = s.stage !== "approve";  // read-only once filming has begun
      // rebuild ONLY when the board actually changed — a rebuild every poll
      // re-fetches every image (cache-buster) and the grid visibly blinks
      if (boardSig(s, ro) !== window.__boardSig) showBoard(s, ro);
      else $("board").style.display = "block";
    }
  } else if (view === 4) {  // Film: shots render, then the premiere takes over
    if (s.stage === "done") {
      if ($("liveR").dataset.mode) { $("liveR").dataset.mode = ""; $("liveR").innerHTML = ""; }
      $("cinema").style.display = "block";
    } else if (s.board && (s.board.shots || []).some(function (sh) { return sh.img; })) {
      syncThumbs($("liveR"), "grid-film", "filming", "gwrap", true,
                 s.board.shots.map(function (sh) { return sh.img; }));
    }
  }
}

function sceneOf(s, sh) {
  var scenes = (s.log && s.log.script && s.log.script.scenes) || [];
  for (var i = 0; i < scenes.length; i++)
    if (scenes[i].id === sh.scene_id) return scenes[i];
  return null;
}
function boardSig(s, ro) {
  return (ro ? "ro|" : "rw|") + ((s.board && s.board.shots) || []).map(function (sh) {
    return sh.id + ":" + (sh.img ? 1 : 0) + ":" + (sh.fail || "");
  }).join(",");
}
function showBoard(s, readonly) {
  var b = s.board || {};
  var withImgs = (b.shots || []).some(function (sh) { return sh.img || sh.fail; });
  if (withImgs) {
    var prevScene = null;
    $("shotlist").innerHTML = '<div id="boardgrid" class="v' + opts.fmt + '">' + b.shots.map(function (sh, i) {
      var sc = sceneOf(s, sh);
      // the shot's OWN action (each frame differs) + the scene setting only when
      // the scene changes — so shots in one scene don't all read identically
      var setting = (sc && sh.scene_id !== prevScene) ? '<b>' + esc2(sc.setting) + '.</b> ' : "";
      var act = esc2(sh.action || (sc ? sc.action : "") || (sh.prompt || "").split(". ").pop().slice(0, 90));
      var scene = setting + act;
      prevScene = sh.scene_id;
      var failText = sh.fail === "moderation" ? "BLOCKED BY MODERATION"
                   : sh.fail === "rate limit" ? "RATE LIMITED"
                   : "GENERATION FAILED";
      return '<div class="bcell" draggable="true" data-id="' + sh.id + '"><span class="bn">' + String(i + 1).padStart(2, "0") + '</span>' +
        '<span class="bx"><button class="bbtn rd" title="redraw">\u21BB</button>' +
        '<button class="bbtn dr" title="remove">\u2715</button></span>' +
        '<div class="bimg">' +
        (sh.img
          ? '<img src="/video?p=' + encodeURIComponent(sh.img) + '&t=' + Date.now() + '">'
          : '<div class="bfall"><span class="bfi">\u26A0\uFE0F</span><span class="bft">' + failText + '</span>' +
            '<button class="bfbtn">Regenerate</button></div>') +
        '<div class="rnote"><input maxlength="200" placeholder="what to fix? (optional)">' +
        '<button class="rgo" title="redraw">\u21BB</button></div></div>' +
        '<div class="bs">' + (sh.subtitle || "") + '</div>' +
        '<div class="bscene">' + scene + '</div></div>';
    }).join("") + "</div>";
    if (readonly) {
      $("shotlist").querySelectorAll(".bx, .rnote").forEach(function (el) { el.style.display = "none"; });
      $("shotlist").querySelectorAll(".bcell").forEach(function (c) { c.removeAttribute("draggable"); });
    } else {
      wireBoardCells(s);
    }
  } else {
    $("shotlist").innerHTML = (b.shots || []).map(function (sh) {
      return '<div class="shot"><span class="sn">' + String(sh.id).padStart(2, "0") + '</span>' +
        '<span class="st">' + (sh.subtitle || "") +
        '<span class="sp">' + (sh.prompt || "").slice(0, 90) + '…</span></span></div>';
    }).join("");
  }
  var nFail = (b.shots || []).filter(function (sh) { return !sh.img; }).length;
  $("barInfo").textContent = nFail
    ? (b.shots || []).length + " frames \u00B7 " + nFail + " blocked \u2014 fix or remove them to film"
    : (b.shots || []).length + " frames \u00B7 voiced";
  $("film").disabled = nFail > 0;  // no fallbacks: never film an incomplete board
  $("film").textContent = b.estimate ? "Film it \u00B7 ~$" + Math.round(b.estimate) : "Film it";
  $("film").onclick = function () {
    var btn = this; btn.disabled = true;
    fetch("/approve", { method: "POST" }).then(function (r) {
      if (!r.ok) {  // the run is gone (e.g. server restarted) \u2014 don't hang on a dead board
        reportErr("this run ended \u2014 reloading");
        setTimeout(function () { location.reload(); }, 900);
        return;
      }
      t0 = Date.now();
      $("board").style.display = "none";
      $("stBar").classList.remove("show");
      poll();
    }).catch(function () { btn.disabled = false; reportErr("could not start filming \u2014 server unreachable"); });
  };
  $("board").style.display = "block";
  window.__boardSig = boardSig(s, !!readonly);
}

function wireBoardCells(s) {
  var cells = document.querySelectorAll ? document.querySelectorAll(".bcell") : [];
  cells.forEach(function (cell) {
    var id = +cell.dataset.id;
    var shot = (s.board.shots || []).filter(function (x) { return x.id === id; })[0] || {};
    var rd = cell.querySelector(".rd"), dr = cell.querySelector(".dr");
    var form = cell.querySelector(".rnote"), input = form && form.querySelector("input");
    if ((s.board.shots || []).length <= 1 && dr) dr.disabled = true;

    function runRedraw() {
      if (cell.classList.contains("rf")) return;
      var note = input ? input.value.trim() : "";
      if (form) form.classList.remove("open");
      cell.classList.add("rf"); rd.disabled = true;
      var wasFailed = !shot.img;  // a blocked frame being fixed
      // send the shot's own data (survives restart) + optional director's note;
      // a blocked frame has no file yet — redraw writes to its intended path
      fetch("/redraw", { method: "POST", headers: { "Content-Type": "application/json" },
                         body: JSON.stringify({ id: id, img: shot.img || shot.imgpath,
                                                prompt: shot.prompt, action: shot.action,
                                                subtitle: shot.subtitle,
                                                size: s.board.size, note: note }) })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          cell.classList.remove("rf"); rd.disabled = false;
          if (res.ok) {
            if (res.d.prompt) shot.prompt = res.d.prompt;  // build future redraws on it
            var textChanged = (res.d.action && res.d.action !== shot.action) ||
                              (res.d.subtitle != null && res.d.subtitle !== shot.subtitle);
            if (res.d.action) shot.action = res.d.action;
            if (res.d.subtitle != null) shot.subtitle = res.d.subtitle;
            if (input) input.value = "";
            if (wasFailed || textChanged) {  // re-render so the caption matches the new frame
              if (wasFailed) { shot.img = res.d.img; shot.fail = ""; }
              window.__boardSig = null;
              showBoard(s);
              return;
            }
            var img = cell.querySelector("img");
            if (img) img.src = "/video?p=" + encodeURIComponent(res.d.img) + "&t=" + Date.now();
          } else { reportErr("redraw: " + (res.d.error || "failed")); }
        })
        .catch(function () { cell.classList.remove("rf"); rd.disabled = false;
                             reportErr("redraw: server unreachable"); });
    }
    // ↻ opens a small note field; a second ↻ (or Enter) fires the redraw
    if (rd) rd.onclick = function () {
      if (!form) { runRedraw(); return; }
      if (form.classList.contains("open")) { runRedraw(); }
      else { form.classList.add("open"); if (input) input.focus(); }
    };
    if (input) input.onkeydown = function (e) {
      if (e.key === "Enter") { e.preventDefault(); runRedraw(); }
      else if (e.key === "Escape") { form.classList.remove("open"); }
    };
    if (form) { var go = form.querySelector(".rgo"); if (go) go.onclick = runRedraw; }
    var bfb = cell.querySelector(".bfbtn");
    if (bfb) bfb.onclick = function (e) { e.stopPropagation(); runRedraw(); };
    if (dr) dr.onclick = function () {
      fetch("/drop", { method: "POST", headers: { "Content-Type": "application/json" },
                       body: JSON.stringify({ id: id }) })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.board) { s.board = d.board; showBoard(s); }
        }).catch(function () {});
    };
    // drag to reorder — but never start a drag from the ↻/✕ buttons or note field
    cell.ondragstart = function (e) {
      if (e.target && e.target.closest && e.target.closest(".bx, .rnote")) { e.preventDefault(); return; }
      dragId = id; cell.classList.add("dragging");
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
    };
    cell.ondragend = function () {
      cell.classList.remove("dragging");
      document.querySelectorAll(".bcell.dragover").forEach(function (c) { c.classList.remove("dragover"); });
    };
    cell.ondragover = function (e) { e.preventDefault(); cell.classList.add("dragover"); };
    cell.ondragleave = function () { cell.classList.remove("dragover"); };
    cell.ondrop = function (e) {
      e.preventDefault(); cell.classList.remove("dragover");
      if (dragId != null && dragId !== id) reorderShots(s, dragId, id);
      dragId = null;
    };
  });
}

var dragId = null;
function reorderShots(s, fromId, toId) {
  var arr = s.board.shots || [];
  var fi = -1, ti = -1;
  arr.forEach(function (x, i) { if (x.id === fromId) fi = i; if (x.id === toId) ti = i; });
  if (fi < 0 || ti < 0 || fi === ti) return;
  var moved = arr.splice(fi, 1)[0];
  arr.splice(ti, 0, moved);
  showBoard(s);  // renumbers badges by new position
  // persist the new order so the film is shot/voiced in this sequence
  fetch("/reorder", { method: "POST", headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ order: arr.map(function (x) { return x.id; }) }) })
    .catch(function () {});
}

function statusLine(s) {
  var d = s.detail || "";
  if (s.stage === "script") return "writing the screenplay\u2026";
  if (s.stage === "board") return "planning the shots\u2026";
  if (s.stage === "critic") return "the critic is reviewing\u2026";
  if (s.stage === "stills") {
    if (d.indexOf("casting") === 0) return d + " \u00B7 drawing character sheets\u2026";
    if (d.indexOf("retrying") === 0) return d + "\u2026";
    return "painting frames" + (d ? " " + d : "") + "\u2026";
  }
  if (s.stage === "voice") return "recording voices" + (d ? " " + d : "") + "\u2026";
  if (s.stage === "film") return "rendering shots" + (d ? " " + d : "") + "\u2026";
  if (s.stage === "cut") return "assembling the film\u2026";
  return "";
}
var __pollState = null;
function poll0() {  // re-render from the last status without refetching
  if (__pollState) { renderCrumbs(__pollState); renderStage(__pollState); }
}
function poll() {
  fetch("/status").then(function (r) { return r.json(); }).then(function (s) {
   try {
    // run vanished (server restarted / reset) while we're showing it — recover
    if (s.stage === "idle" && document.body.classList.contains("studio")) {
      location.reload();
      return;
    }
    __pollState = s;
    if (s.title) $("runTitle").textContent = "\u201C" + s.title + "\u201D";
    if (s.input) $("runsub").innerHTML = "\u201C" + esc2(s.input.logline) + "\u201D " +
      '<span class="rsopts">\u00B7 ' + esc2(s.input.cast) + ' \u00B7 ' + s.input.secs + 's</span>';
    $("stStatus").textContent = statusLine(s);
    // arriving at the gate or the premiere always pulls the user there
    if (s.stage !== window.__lastStage && (s.stage === "approve" || s.stage === "done")) userView = null;
    renderCrumbs(s);
    renderStage(s);
    var snap = "stage=" + s.stage + " view=" + (userView === null ? "live" : userView) +
               " panel=" + $("panelText").innerHTML.length + " liveR=" + $("liveR").innerHTML.length +
               " logKeys=" + Object.keys(s.log || {}).join(",");
    if (location.search.indexOf("dbg") >= 0) { $("dbg").style.display = "block"; $("dbg").textContent = snap; }
    if (s.stage !== window.__lastStage) {
      window.__lastStage = s.stage;
      fetch("/clientlog", { method: "POST", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ err: "[telemetry] " + snap }) }).catch(function () {});
    }
    if (s.stage === "approve") {
      $("stBar").classList.add("show");
      $("barApprove").style.display = "flex"; $("barDone").style.display = "none";
      setTimeout(poll, 1200); return;
    }
    if (s.stage === "done") {
      $("player").src = s.video;
      $("dl").href = s.video;
      $("title").textContent = s.title || "";
      var nsh = (s.board && s.board.shots || []).length;
      $("meta").textContent = "$" + (+s.cost).toFixed(2) + (nsh ? " \u00B7 " + nsh + " shots" : "");
      $("cap").textContent = s.caption || "";
      function copyCap() {
        navigator.clipboard.writeText(s.caption || "");
        var lbl = $("caplbl"), was = lbl.textContent;
        lbl.textContent = "Copied \u2713";
        setTimeout(function () { lbl.textContent = was; }, 1400);
      }
      $("copycap").onclick = copyCap;
      $("cap").onclick = copyCap;
      // mobile: system share sheet with the actual video file -> TikTok in 2 taps
      try {
        var probe = new File([""], "p.mp4", { type: "video/mp4" });
        if (navigator.canShare && navigator.canShare({ files: [probe] })) {
          $("ttshare").style.display = "inline-flex";
          $("ttshare").onclick = function () {
            fetch(s.video).then(function (r) { return r.blob(); }).then(function (b) {
              var f = new File([b], "drama916.mp4", { type: "video/mp4" });
              return navigator.share({ files: [f], text: s.caption || "" });
            }).catch(function () {});
          };
        }
      } catch (e) {}
      $("stBar").classList.add("show");
      $("barApprove").style.display = "none"; $("barDone").style.display = "flex";
      $("barInfo").textContent = "$" + (+s.cost).toFixed(2);
      $("player").play().catch(function () {});
      loadVids();
      return;
    }
    $("stBar").classList.remove("show");
    if (s.stage === "error") {
      document.body.classList.remove("studio");
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
        if self.path == "/reorder":
            n = int(self.headers.get("Content-Length", 0))
            order = json.loads(self.rfile.read(n) or b"{}").get("order") or []
            with lock:
                b = state.get("board")
                if state["stage"] != "approve" or not b:
                    return self._json(409, {"error": "not at the approval gate"})
                pos = {sid: i for i, sid in enumerate(order)}
                b["shots"].sort(key=lambda s: pos.get(s["id"], 1e9))
                current_approve["edits"]["order"] = list(order)
                return self._json(200, {"ok": True})
        if self.path == "/redraw":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            sid = req.get("id")
            # Redraw only regenerates a preview PNG from a prompt — it spends no
            # video credit and needs no live pipeline thread. Prefer server state
            # (normal case); fall back to client-supplied shot data so a redraw
            # still works after a server restart orphaned the run.
            with lock:
                b = state.get("board")
                shot = next((s for s in (b or {}).get("shots", []) if s["id"] == sid), None) if b else None
                size = (b or {}).get("size") if b else None
            prompt = (shot or {}).get("prompt") or req.get("prompt")
            action = (shot or {}).get("action") or req.get("action") or ""
            subtitle = (shot or {}).get("subtitle") or req.get("subtitle") or ""
            img = (shot or {}).get("img") or req.get("img")
            size = size or req.get("size") or "720*1280"
            note = str(req.get("note", "")).strip()[:200]
            if not img or not prompt:
                return self._json(404, {"error": "shot not found"})
            runs = (Path(__file__).parent / "runs").resolve()
            out = Path(img).resolve()
            if out.suffix != ".png" or not out.is_relative_to(runs) or not out.parent.is_dir():
                return self._json(400, {"error": "invalid frame path"})
            from showrunner.ledger import Ledger
            from showrunner.storyboard import generate_still
            ledger = Ledger()
            # a director's note steers the redraw AND keeps the shot's text in
            # sync: the caption (action) follows the new staging; the spoken
            # line changes only when the note explicitly asks for it
            if note:
                from showrunner import config as srconfig
                from showrunner.llm import chat_json
                try:
                    rw = chat_json("redraw_note", srconfig.MODEL_CHEAP,
                                   "You adjust ONE storyboard frame per a director's note. "
                                   "Keep the same characters, wardrobe and visual style; change "
                                   "only what the note asks. Reply ONLY JSON: "
                                   '{"prompt": str,   full rewritten image prompt; '
                                   '"action": str,   short plain description of what now happens '
                                   "(no style/camera words); "
                                   '"subtitle": str   the spoken line - return it UNCHANGED unless '
                                   "the note explicitly changes what is said}",
                                   f"PROMPT: {prompt}\nACTION: {action}\nSUBTITLE: {subtitle}\n"
                                   f"DIRECTOR'S NOTE: {note}",
                                   ledger, thinking=False)
                    prompt = str(rw.get("prompt") or prompt)
                    action = str(rw.get("action") or action)
                    subtitle = str(rw.get("subtitle") if rw.get("subtitle") is not None else subtitle)
                except Exception:
                    prompt = prompt + " " + note  # fallback: just append the note
            refs = sorted(out.parent.parent.glob("cast/*.png")) or None
            try:  # синхронно: 12-30с; фронт показує frost на комірці
                generate_still(prompt, size, out, ledger, refs=refs)
            except Exception as e:
                detail = getattr(getattr(e, "response", None), "text", "") or str(e)
                return self._json(502, {"error": detail[:200]})
            # persist into live state AND into the approval edits, so the film
            # is shot/voiced with the redrawn prompt/action/line — not the old text
            with lock:
                lb = state.get("board")
                if lb:
                    for s2 in lb.get("shots", []):
                        if s2["id"] == sid:
                            s2["prompt"] = prompt
                            s2["action"] = action
                            s2["subtitle"] = subtitle
                current_approve["edits"].setdefault("mods", {})[sid] = {
                    "prompt": prompt, "action": action, "subtitle": subtitle}
            return self._json(200, {"ok": True, "img": img, "prompt": prompt,
                                    "action": action, "subtitle": subtitle})
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
