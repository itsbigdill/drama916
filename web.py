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
<style>
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; font: 16px/1.5 -apple-system, system-ui;
         color: #F2F0EA; background: #0D0E12; display: flex; flex-direction: column;
         align-items: center; padding: 48px 18px; }
  body::before { content: ""; position: fixed; inset: 0; z-index: -1; background:
    radial-gradient(55% 40% at 20% 10%, rgba(221,122,81,.14), transparent 70%),
    radial-gradient(50% 45% at 85% 20%, rgba(122,140,220,.12), transparent 70%),
    radial-gradient(70% 50% at 50% 105%, rgba(122,199,204,.10), transparent 70%); }
  .wordmark { font-size: 22px; font-weight: 800; letter-spacing: -.01em; margin-bottom: 26px; }
  .dot { color: #E8A15C; }
  .glass { width: 100%; max-width: 560px; border-radius: 28px; padding: 22px;
           background: linear-gradient(165deg, rgba(255,255,255,.09), rgba(255,255,255,.045));
           border: 1px solid rgba(255,255,255,.14);
           backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
           box-shadow: 0 30px 70px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.12); }
  textarea { width: 100%; border: 0; resize: none; background: rgba(255,255,255,.07);
             border-radius: 16px; padding: 16px; font: inherit; color: inherit;
             outline: none; min-height: 84px; }
  textarea::placeholder { color: rgba(242,240,234,.35); }
  .row { display: flex; gap: 10px; align-items: center; margin-top: 14px; }
  .chip { border: 1px solid rgba(255,255,255,.18); background: transparent; cursor: pointer;
          color: rgba(242,240,234,.55); border-radius: 999px; padding: 8px 14px;
          font: 600 13px -apple-system, system-ui; }
  .chip.on { background: rgba(232,161,92,.18); border-color: rgba(232,161,92,.5); color: #E8A15C; }
  .go { flex: 1; border: 0; border-radius: 16px; padding: 15px; cursor: pointer;
        background: #E8A15C; color: #14100B; font: 800 16px -apple-system, system-ui;
        box-shadow: 0 10px 30px rgba(232,161,92,.35); }
  .go:disabled { opacity: .4; box-shadow: none; }

  #steps { display: none; justify-content: space-between; margin: 26px 6px 2px; }
  .step { text-align: center; flex: 1; font-size: 12px; font-weight: 700;
          color: rgba(242,240,234,.3); }
  .step .d { width: 10px; height: 10px; border-radius: 50%; margin: 0 auto 7px;
             background: rgba(255,255,255,.15); }
  .step.on { color: #E8A15C; }
  .step.on .d { background: #E8A15C; box-shadow: 0 0 14px rgba(232,161,92,.9);
                animation: pulse 1.2s ease-in-out infinite; }
  .step.done { color: rgba(242,240,234,.75); }
  .step.done .d { background: rgba(242,240,234,.75); }
  @keyframes pulse { 50% { transform: scale(1.35); } }
  #detail { text-align: center; font-size: 13px; color: rgba(242,240,234,.45);
            margin-top: 12px; min-height: 18px; }

  #cinema { display: none; margin-top: 20px; }
  #cinema video { width: 100%; max-height: 64vh; object-fit: contain; background: #000;
                  border-radius: 18px; display: block;
                  box-shadow: 0 20px 50px rgba(0,0,0,.5); }
  #cap { font-size: 13.5px; color: rgba(242,240,234,.6); background: rgba(255,255,255,.06);
         border-radius: 12px; padding: 11px 13px; margin: 12px 0 2px; white-space: pre-wrap; }
  #cap:empty { display: none; }
  a.chip { text-decoration: none; display: inline-block; }
  #title { font-weight: 800; font-size: 18px; margin: 14px 2px 2px; }
  #meta { font-size: 13px; color: rgba(242,240,234,.45); margin: 2px; }
  .ghost { margin-top: 14px; border: 0; background: transparent; cursor: pointer;
           color: rgba(242,240,234,.5); font: 700 14px -apple-system, system-ui; }
  #err { display: none; margin-top: 16px; font-size: 14px; color: #E8907C; }
  .foot { margin-top: 22px; font-size: 12px; }
  .foot a { color: rgba(242,240,234,.35); }
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
