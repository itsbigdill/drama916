"""Showrunner web UI — one glass page: logline in, film out.

    python web.py            # http://localhost:8090

Stdlib-only server (no new deps). One run at a time (it's a demo, not a farm).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from showrunner import pipeline  # noqa: E402

PORT = 8090

# single-run job state, updated by the pipeline's progress callback
state = {"running": False, "stage": "idle", "detail": "", "video": None,
         "cost": None, "error": None, "title": "", "caption": "", "log": {},
         "board": None}
lock = threading.Lock()
approve_event = threading.Event()


def start_run(logline: str, dry_run: bool, vertical: bool,
              shots_target: int = 12, genre: str = "", cast: str = ""):
    def cb(stage: str, detail: str):
        with lock:
            if stage == "approve":
                state["stage"] = "approve"
                state["board"] = json.loads(detail)
                return
            if stage == "done":
                d = json.loads(detail)
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
                         approval=approve_event.wait,
                         shots_target=shots_target, genre=genre, cast=cast)
        except BaseException as e:  # SystemExit included (budget cap)
            with lock:
                state.update(error=str(e), running=False, stage="error")

    approve_event.clear()
    with lock:
        state.update(running=True, stage="script", detail="", video=None,
                     cost=None, error=None, title="", caption="", log={}, board=None)
    threading.Thread(target=job, daemon=True).start()


PAGE = r"""<!doctype html><meta charset="utf-8"><title>showrunner</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Unbounded:wght@500;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; font: 16px/1.5 -apple-system, system-ui;
         color: #F4F0FF; background: #08070E; display: flex; flex-direction: column;
         align-items: center; padding: 48px 18px; }
  body::before { content: ""; position: fixed; inset: 0; z-index: -1; background:
    radial-gradient(60% 45% at 15% 8%, rgba(124,92,255,.2), transparent 70%),
    radial-gradient(45% 40% at 88% 12%, rgba(255,64,64,.12), transparent 70%),
    radial-gradient(75% 55% at 50% 108%, rgba(64,160,255,.1), transparent 70%); }
  .mono { font-family: "JetBrains Mono", monospace; }
  .wordmark { font-family: "Unbounded", system-ui; font-weight: 800; font-size: 30px;
              letter-spacing: -.02em; margin-bottom: 28px;
              background: linear-gradient(180deg, #FFFFFF 20%, #A08CFF 140%);
              -webkit-background-clip: text; background-clip: text; color: transparent;
              filter: drop-shadow(0 14px 34px rgba(124,92,255,.5)); }
  .dot { color: #FF4D45; -webkit-text-fill-color: #FF4D45; }
  .glass { width: 100%; max-width: 600px; border-radius: 30px; padding: 26px;
           background: linear-gradient(168deg, rgba(255,255,255,.1), rgba(255,255,255,.035));
           border: 1px solid rgba(255,255,255,.15);
           backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
           box-shadow: 0 46px 100px rgba(0,0,0,.6), 0 12px 30px rgba(124,92,255,.12),
                       inset 0 2px 0 rgba(255,255,255,.16), inset 0 -24px 50px rgba(124,92,255,.05); }
  textarea { width: 100%; border: 0; resize: none; background: rgba(8,7,14,.55);
             border-radius: 18px; padding: 18px 20px; font-size: 17px; line-height: 1.55;
             font-family: inherit; color: inherit; outline: none; min-height: 96px;
             box-shadow: inset 0 3px 14px rgba(0,0,0,.55), inset 0 -1px 0 rgba(255,255,255,.05); }
  textarea::placeholder { color: rgba(244,240,255,.3); }
  .row { display: flex; gap: 12px; align-items: stretch; margin-top: 16px; }
  .seg { display: inline-flex; gap: 0; border-radius: 14px; overflow: hidden;
         border: 1px solid rgba(255,255,255,.12); }
  .seg .chip { border: 0; border-radius: 0; padding: 10px 15px; }
  .seg .chip + .chip { border-left: 1px solid rgba(255,255,255,.1); }
  .chip { border: 1px solid rgba(255,255,255,.12); cursor: pointer; background: transparent;
          color: rgba(244,240,255,.4); border-radius: 14px; padding: 0 16px;
          font-family: "JetBrains Mono", monospace; font-size: 13px; font-weight: 700; }
  .chip.on { background: linear-gradient(180deg, rgba(124,92,255,.5), rgba(124,92,255,.22));
             border-color: rgba(170,148,255,.8); color: #E6DFFF;
             box-shadow: 0 8px 22px rgba(124,92,255,.4), inset 0 1px 0 rgba(255,255,255,.3); }
  .go { flex: 1; border: 0; border-radius: 16px; padding: 17px; cursor: pointer;
        background: linear-gradient(180deg, #FF5A4E, #C92222);
        color: #FFF6F4; font-family: "Unbounded", system-ui; font-weight: 800;
        font-size: 15px; letter-spacing: .12em; text-transform: uppercase;
        box-shadow: 0 20px 45px rgba(226,61,61,.4), 0 4px 10px rgba(0,0,0,.4),
                    inset 0 2px 0 rgba(255,255,255,.35), inset 0 -4px 10px rgba(110,8,8,.55);
        transition: transform .15s ease; }
  .go:hover { transform: translateY(-2px); }
  .go:disabled { opacity: .35; box-shadow: none; transform: none; }

  #steps { display: none; justify-content: space-between; margin: 28px 4px 0; }
  .step { text-align: center; flex: 1; font-family: "JetBrains Mono", monospace;
          font-size: 11px; font-weight: 700; letter-spacing: .14em;
          color: rgba(244,240,255,.25); }
  .step .d { width: 13px; height: 13px; border-radius: 50%; margin: 0 auto 8px;
             background: rgba(255,255,255,.12); box-shadow: inset 0 2px 3px rgba(0,0,0,.45); }
  .step.on { color: #CFC2FF; }
  .step.on .d { background: radial-gradient(circle at 35% 30%, #E4DBFF, #7C5CFF);
                box-shadow: 0 0 18px rgba(124,92,255,.95), inset 0 1px 1px rgba(255,255,255,.6);
                animation: pulse 1.2s ease-in-out infinite; }
  .step.done { color: rgba(244,240,255,.65); }
  .step.done .d { background: radial-gradient(circle at 35% 30%, #FFF, #B9AEDB);
                  box-shadow: inset 0 1px 1px rgba(255,255,255,.7); }
  @keyframes pulse { 50% { transform: scale(1.4); } }
  #detail { text-align: center; font-family: "JetBrains Mono", monospace; font-size: 12.5px;
            color: rgba(244,240,255,.45); margin-top: 12px; min-height: 18px; }

  #shotlist { margin-top: 14px; }
  .shot { display: flex; gap: 12px; align-items: baseline; padding: 9px 4px;
          border-top: 1px solid rgba(255,255,255,.07); }
  .shot .sn { font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700;
              color: #A08CFF; flex: 0 0 26px; }
  .shot .st { font-size: 14px; color: rgba(244,240,255,.78); }
  .shot .sp { font-size: 12px; color: rgba(244,240,255,.38); display: block; margin-top: 1px; }
  #feed { margin-top: 6px; display: none; }
  .frow { display: flex; gap: 12px; align-items: baseline; padding: 10px 4px;
          border-top: 1px solid rgba(255,255,255,.07); }
  .frow .fl { font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700;
              letter-spacing: .12em; color: #A08CFF; flex: 0 0 64px; }
  .frow .fv { font-size: 14.5px; color: rgba(244,240,255,.85); }
  .frow .fv b { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 13.5px; }

  #cinema { display: none; margin-top: 22px; }
  #cinema video { width: 100%; max-height: 64vh; object-fit: contain; background: #000;
                  border-radius: 20px; display: block;
                  box-shadow: 0 30px 70px rgba(0,0,0,.65), 0 6px 20px rgba(124,92,255,.2),
                              inset 0 1px 0 rgba(255,255,255,.1); }
  #cap { font-size: 14px; color: rgba(244,240,255,.62); background: rgba(8,7,14,.55);
         border-radius: 14px; padding: 13px 16px; margin: 14px 0 2px; white-space: pre-wrap;
         box-shadow: inset 0 2px 10px rgba(0,0,0,.45); }
  #cap:empty { display: none; }
  a.chip { text-decoration: none; display: inline-flex; align-items: center; }
  #title { font-family: "Unbounded", system-ui; font-weight: 500; font-size: 22px;
           margin: 16px 2px 2px; filter: drop-shadow(0 10px 26px rgba(124,92,255,.4)); }
  #meta { font-family: "JetBrains Mono", monospace; font-size: 12px;
          color: rgba(244,240,255,.42); margin: 4px 2px; }
  .ghost { border: 0; background: transparent; cursor: pointer; padding: 0 8px;
           color: rgba(244,240,255,.45); font: 700 13px -apple-system, system-ui; }
  #err { display: none; margin-top: 16px; font-size: 14px; color: #FF9A8F; }
  .foot { margin-top: 26px; font-size: 12px; }
  .foot a { color: rgba(244,240,255,.3); }
</style>
<body>
<div class="wordmark">showrunner<span class="dot">.</span></div>

<div class="glass">
  <textarea id="log" placeholder="One line. A whole film."></textarea>
  <div class="row" style="flex-wrap:wrap">
    <span class="seg" data-k="fmt"><button class="chip on" data-v="916">9:16</button><button class="chip" data-v="169">16:9</button></span>
    <span class="seg" data-k="len"><button class="chip" data-v="3">15s</button><button class="chip" data-v="6">30s</button><button class="chip" data-v="9">45s</button><button class="chip on" data-v="12">60s</button></span>
  </div>
  <div class="row" style="flex-wrap:wrap">
    <span class="seg" data-k="genre"><button class="chip" data-v="drama">Drama</button><button class="chip" data-v="comedy">Comedy</button><button class="chip" data-v="noir">Noir</button><button class="chip" data-v="comic book style">Comic</button><button class="chip" data-v="ad">Ad</button></span>
    <span class="seg" data-k="cast"><button class="chip" data-v="realistic human characters">Real</button><button class="chip" data-v="anthropomorphic fruit and vegetable characters">Fruits</button><button class="chip" data-v="animal characters">Animals</button><button class="chip" data-v="everyday objects brought to life as characters">Objects</button></span>
  </div>
  <div class="row">
    <button id="go" class="go">Action</button>
  </div>

  <div id="steps">
    <div class="step" data-s="script"><div class="d"></div>SCRIPT</div>
    <div class="step" data-s="board"><div class="d"></div>BOARD</div>
    <div class="step" data-s="critic"><div class="d"></div>CRITIC</div>
    <div class="step" data-s="film"><div class="d"></div>FILM</div>
    <div class="step" data-s="dailies"><div class="d"></div>DAILIES</div>
    <div class="step" data-s="cut"><div class="d"></div>CUT</div>
  </div>
  <div id="detail"></div>
  <div id="feed"></div>

  <div id="board" style="display:none">
    <div id="shotlist"></div>
    <div class="row" style="margin-top:18px">
      <button id="film" class="go">Film it</button>
      <button class="ghost" onclick="location.reload()">Start over</button>
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
      <button class="ghost" onclick="location.reload()" style="margin-left:auto">New film</button>
    </div>
  </div>
  <div id="err"></div>
</div>

<div class="foot"><a href="https://www.qwencloud.com">Qwen + HappyHorse on Alibaba Cloud</a></div>

<script>
var $ = function (id) { return document.getElementById(id); };
var ORDER = ["script", "board", "critic", "film", "dailies", "cut"];
var t0 = null;
var opts = { fmt: "916", len: "12", genre: "", cast: "" };
document.querySelectorAll(".seg").forEach(function (seg) {
  var k = seg.dataset.k;
  var optional = (k === "genre" || k === "cast");   // ці групи можна зняти
  seg.querySelectorAll(".chip").forEach(function (ch) {
    ch.onclick = function () {
      var was = ch.classList.contains("on");
      seg.querySelectorAll(".chip").forEach(function (x) { x.classList.remove("on"); });
      if (optional && was) { opts[k] = ""; return; }
      ch.classList.add("on");
      opts[k] = ch.dataset.v;
    };
  });
});

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
  if (!logline) { $("log").focus(); return; }
  $("go").disabled = true; $("log").disabled = true; t0 = Date.now();
  fetch("/run", { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ logline: logline, vertical: opts.fmt === "916",
                                         shots: +opts.len, genre: opts.genre, cast: opts.cast }) })
    .then(function () { $("steps").style.display = "flex"; $("feed").style.display = "block"; poll(); });
};

function feedRows(s) {
  var L = s.log || {}, rows = [];
  if (L.script) rows.push(["SCRIPT", "<b>“" + (L.script.title || "") + "”</b> · " + L.script.scenes + " scenes"]);
  if (L.board) rows.push(["BOARD", L.board.shots + " shots planned"]);
  if (L.critic) rows.push(["CRITIC", (L.critic.score != null ? L.critic.score + "/10" : "approved") + " · " + L.critic.rounds + " round" + (L.critic.rounds > 1 ? "s" : "")]);
  if (L.dailies) rows.push(["DAILIES", L.dailies.reshot
        ? L.dailies.reshot + " take" + (L.dailies.reshot > 1 ? "s" : "") + " reshot — " + (L.dailies.last_reason || "")
        : "all " + L.dailies.approved + " takes approved"]);
  $("feed").innerHTML = rows.map(function (r) {
    return '<div class="frow"><span class="fl">' + r[0] + ' ✓</span><span class="fv">' + r[1] + "</span></div>";
  }).join("");
}

function showBoard(s) {
  var b = s.board || {};
  $("shotlist").innerHTML = (b.shots || []).map(function (sh) {
    return '<div class="shot"><span class="sn">' + String(sh.id).padStart(2, "0") + '</span>' +
      '<span class="st">' + (sh.subtitle || "") +
      '<span class="sp">' + (sh.prompt || "").slice(0, 90) + '…</span></span></div>';
  }).join("");
  $("film").textContent = b.estimate ? "Film it · ~$" + Math.round(b.estimate) : "Film it";
  $("film").onclick = function () {
    this.disabled = true;
    fetch("/approve", { method: "POST" }).then(function () {
      $("board").style.display = "none"; poll();
    });
  };
  $("board").style.display = "block";
}

function poll() {
  fetch("/status").then(function (r) { return r.json(); }).then(function (s) {
    var isApprove = s.stage === "approve";
    var idx = isApprove ? 3 : ORDER.indexOf(s.stage);
    document.querySelectorAll(".step").forEach(function (el, i) {
      el.className = "step" + (i < idx || s.stage === "done" ? " done"
        : (i === idx && !isApprove) ? " on" : "");
    });
    feedRows(s);
    if (isApprove) { $("detail").textContent = ""; showBoard(s); return; }
    var el = Math.round((Date.now() - t0) / 1000);
    $("detail").textContent =
      s.stage === "film" && s.detail ? "shot " + s.detail + " · " + el + "s" :
      s.stage === "dailies" && s.detail ? "reviewing " + s.detail + " · " + el + "s" :
      s.stage !== "done" ? el + "s" : "";
    if (s.stage === "done") {
      $("steps").style.display = "none"; $("detail").textContent = "";
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
      return;
    }
    if (s.stage === "error") {
      $("err").style.display = "block"; $("err").textContent = s.error || "failed";
      $("go").disabled = false; $("log").disabled = false;
      return;
    }
    setTimeout(poll, 1200);
  });
}
</script>"""


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
        elif path == "/status":
            with lock:
                self._json(200, dict(state))
        elif path == "/video":
            # only serve mp4s that live under runs/ — no path traversal
            p = Path(self.path.split("p=", 1)[-1]).resolve()
            runs = (Path(__file__).parent / "runs").resolve()
            if p.suffix == ".mp4" and p.is_file() and p.is_relative_to(runs):
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json(404, {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/approve":
            approve_event.set()
            with lock:
                if state["stage"] == "approve":
                    state["stage"] = "film"
                    state["board"] = None
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
                  shots_target=shots, genre=genre, cast=cast)
        self._json(200, {"ok": True})


if __name__ == "__main__":
    print(f"showrunner web → http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
