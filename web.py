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
         "cost": None, "error": None, "title": "", "caption": ""}
lock = threading.Lock()


def start_run(logline: str, dry_run: bool, vertical: bool):
    def cb(stage: str, detail: str):
        with lock:
            if stage == "script" and detail:
                state["title"] = detail
            if stage == "done":
                d = json.loads(detail)
                state.update(stage="done", detail="", cost=str(d["cost"]),
                             caption=d.get("caption", ""),
                             video="/video?p=" + d["video"], running=False)
            else:
                state.update(stage=stage, detail=detail)

    def job():
        try:
            pipeline.run(logline, dry_run=dry_run, cb=cb, vertical=vertical)
        except BaseException as e:  # SystemExit included (budget cap)
            with lock:
                state.update(error=str(e), running=False, stage="error")

    with lock:
        state.update(running=True, stage="script", detail="", video=None,
                     cost=None, error=None, title="", caption="")
    threading.Thread(target=job, daemon=True).start()


PAGE = r"""<!doctype html><meta charset="utf-8"><title>showrunner</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; font: 16px/1.5 -apple-system, system-ui;
         color: #F4F0FF; background: #0A0812; display: flex; flex-direction: column;
         align-items: center; padding: 52px 18px; }
  /* studio spotlights: violet key, red record light, cold rim */
  body::before { content: ""; position: fixed; inset: 0; z-index: -1; background:
    radial-gradient(60% 45% at 15% 8%, rgba(124,92,255,.22), transparent 70%),
    radial-gradient(45% 40% at 88% 12%, rgba(255,64,64,.14), transparent 70%),
    radial-gradient(75% 55% at 50% 108%, rgba(64,160,255,.12), transparent 70%); }
  .serif { font-family: "Instrument Serif", Georgia, serif; font-style: italic; }
  .wordmark { font-family: "Instrument Serif", Georgia, serif; font-style: italic;
              font-size: 52px; line-height: 1; letter-spacing: -.01em; margin-bottom: 30px;
              text-shadow: 0 2px 0 rgba(255,255,255,.08), 0 18px 50px rgba(124,92,255,.45); }
  .dot { color: #FF4D45; font-style: normal; }
  .glass { width: 100%; max-width: 580px; border-radius: 34px; padding: 26px;
           background: linear-gradient(168deg, rgba(255,255,255,.11), rgba(255,255,255,.04));
           border: 1px solid rgba(255,255,255,.16);
           backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
           box-shadow: 0 46px 100px rgba(0,0,0,.6), 0 12px 30px rgba(124,92,255,.12),
                       inset 0 2px 0 rgba(255,255,255,.16), inset 0 -24px 50px rgba(124,92,255,.06); }
  textarea { width: 100%; border: 0; resize: none; background: rgba(10,8,18,.5);
             border-radius: 20px; padding: 19px 20px; font-size: 18px; line-height: 1.5;
             font-family: inherit; color: inherit; outline: none; min-height: 100px;
             box-shadow: inset 0 3px 14px rgba(0,0,0,.5), inset 0 -1px 0 rgba(255,255,255,.06); }
  textarea::placeholder { color: rgba(244,240,255,.32);
             font-family: "Instrument Serif", Georgia, serif; font-style: italic; }
  .row { display: flex; gap: 12px; align-items: center; margin-top: 16px; }
  .chip { border: 1px solid rgba(255,255,255,.2); cursor: pointer;
          background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.02));
          color: rgba(244,240,255,.6); border-radius: 999px; padding: 11px 18px;
          font: 700 14px -apple-system, system-ui;
          box-shadow: 0 6px 16px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.12); }
  .chip.on { background: linear-gradient(180deg, rgba(124,92,255,.4), rgba(124,92,255,.2));
             border-color: rgba(158,132,255,.7); color: #CFC2FF;
             box-shadow: 0 6px 20px rgba(124,92,255,.35), inset 0 1px 0 rgba(255,255,255,.25); }
  .go { flex: 1; border: 0; border-radius: 20px; padding: 17px; cursor: pointer;
        background: linear-gradient(180deg, #FF5A4E, #D62B2B);
        color: #FFF6F4; font-family: "Instrument Serif", Georgia, serif;
        font-style: italic; font-size: 24px;
        box-shadow: 0 20px 45px rgba(226,61,61,.45), 0 4px 10px rgba(0,0,0,.4),
                    inset 0 2px 0 rgba(255,255,255,.38), inset 0 -3px 8px rgba(120,10,10,.5);
        transition: transform .15s ease; }
  .go:hover { transform: translateY(-2px); }
  .go:disabled { opacity: .4; box-shadow: none; transform: none; }

  #steps { display: none; justify-content: space-between; margin: 30px 6px 2px; }
  .step { text-align: center; flex: 1; font-size: 12px; font-weight: 800;
          letter-spacing: .1em; text-transform: uppercase; color: rgba(244,240,255,.28); }
  .step .d { width: 14px; height: 14px; border-radius: 50%; margin: 0 auto 9px;
             background: rgba(255,255,255,.14);
             box-shadow: inset 0 2px 3px rgba(0,0,0,.4); }
  .step.on { color: #CFC2FF; }
  .step.on .d { background: radial-gradient(circle at 35% 30%, #E4DBFF, #7C5CFF);
                box-shadow: 0 0 20px rgba(124,92,255,.95), inset 0 1px 1px rgba(255,255,255,.6);
                animation: pulse 1.2s ease-in-out infinite; }
  .step.done { color: rgba(244,240,255,.72); }
  .step.done .d { background: radial-gradient(circle at 35% 30%, #FFF, #B9AEDB);
                  box-shadow: inset 0 1px 1px rgba(255,255,255,.7); }
  @keyframes pulse { 50% { transform: scale(1.4); } }
  #detail { text-align: center; font-size: 14px; color: rgba(244,240,255,.42);
            margin-top: 14px; min-height: 20px; }

  #cinema { display: none; margin-top: 22px; }
  #cinema video { width: 100%; max-height: 64vh; object-fit: contain; background: #000;
                  border-radius: 22px; display: block;
                  box-shadow: 0 30px 70px rgba(0,0,0,.65), 0 6px 20px rgba(124,92,255,.2),
                              inset 0 1px 0 rgba(255,255,255,.1); }
  #cap { font-size: 14.5px; color: rgba(244,240,255,.62); background: rgba(10,8,18,.5);
         border-radius: 16px; padding: 13px 16px; margin: 14px 0 2px; white-space: pre-wrap;
         box-shadow: inset 0 2px 10px rgba(0,0,0,.4); }
  #cap:empty { display: none; }
  a.chip { text-decoration: none; display: inline-block; }
  #title { font-family: "Instrument Serif", Georgia, serif; font-style: italic;
           font-size: 32px; margin: 16px 2px 2px;
           text-shadow: 0 12px 34px rgba(124,92,255,.4); }
  #meta { font-size: 13px; color: rgba(244,240,255,.42); margin: 2px; }
  .ghost { border: 0; background: transparent; cursor: pointer;
           color: rgba(244,240,255,.48); font: 700 14px -apple-system, system-ui; }
  #err { display: none; margin-top: 16px; font-size: 14px; color: #FF9A8F; }
  .foot { margin-top: 26px; font-size: 12px; }
  .foot a { color: rgba(244,240,255,.32); }
</style>
<body>
<div class="wordmark">showrunner<span class="dot">.</span></div>

<div class="glass">
  <textarea id="log" placeholder="One line. A whole film.&#10;“A robot janitor on a space station finds a houseplant”"></textarea>
  <div class="row">
    <button id="vert" class="chip on">9:16</button>
    <button id="dry" class="chip">$0 test</button>
    <button id="go" class="go">Action</button>
  </div>

  <div id="steps">
    <div class="step" data-s="script"><div class="d"></div>Script</div>
    <div class="step" data-s="board"><div class="d"></div>Board</div>
    <div class="step" data-s="critic"><div class="d"></div>Critic</div>
    <div class="step" data-s="film"><div class="d"></div>Film</div>
    <div class="step" data-s="cut"><div class="d"></div>Cut</div>
  </div>
  <div id="detail"></div>

  <div id="cinema">
    <video id="player" controls playsinline></video>
    <div id="title"></div>
    <div id="meta"></div>
    <div id="cap"></div>
    <div class="row">
      <a id="dl" class="chip" download="showrunner.mp4">Download</a>
      <button id="copycap" class="chip">Copy caption</button>
      <button class="ghost" onclick="location.reload()" style="margin:0 0 0 auto">New film</button>
    </div>
  </div>
  <div id="err"></div>
</div>

<div class="foot"><a href="https://www.qwencloud.com">Qwen + HappyHorse on Alibaba Cloud</a></div>

<script>
var $ = function (id) { return document.getElementById(id); };
var ORDER = ["script", "board", "critic", "film", "cut"];
var dry = false, vert = true;
$("dry").onclick = function () { dry = !dry; this.classList.toggle("on", dry); };
$("vert").onclick = function () { vert = !vert; this.classList.toggle("on", vert); };

$("go").onclick = function () {
  var logline = $("log").value.trim();
  if (!logline) { $("log").focus(); return; }
  $("go").disabled = true; $("log").disabled = true;
  fetch("/run", { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ logline: logline, dry_run: dry, vertical: vert }) })
    .then(function () { $("steps").style.display = "flex"; poll(); });
};

function poll() {
  fetch("/status").then(function (r) { return r.json(); }).then(function (s) {
    var idx = ORDER.indexOf(s.stage);
    document.querySelectorAll(".step").forEach(function (el, i) {
      el.className = "step" + (i < idx || s.stage === "done" ? " done" : i === idx ? " on" : "");
    });
    $("detail").textContent =
      s.stage === "film" && s.detail ? "shot " + s.detail :
      s.stage === "critic" && s.detail ? s.detail : "";
    if (s.stage === "done") {
      $("steps").style.display = "none"; $("detail").textContent = "";
      $("player").src = s.video;
      $("dl").href = s.video;
      $("title").textContent = s.title || "";
      $("meta").textContent = (dry ? "$0 test render" : "cost $" + (+s.cost).toFixed(2));
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
        start_run(logline, bool(body.get("dry_run")), bool(body.get("vertical")))
        self._json(200, {"ok": True})


if __name__ == "__main__":
    print(f"showrunner web → http://localhost:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
