# drama916 — Devpost submission copy

Paste-ready text for the Devpost form. Track: **AI Showrunner**.

---

## Name
drama916

## Tagline (≤ 200 chars)
One logline in, a finished vertical drama out. drama916 writes, storyboards,
*critiques before it renders*, films, and voices a TikTok-ready short — and
shows you the receipt for every cent of Qwen compute it spent.

## Elevator pitch (the "what")
Type one sentence — *"Ronaldo loses the World Cup and Messi comforts him with
cheeseburgers"* — and ~10 minutes later you get a voiced, subtitled, 9:16 short
film. drama916 is an autonomous showrunner: a chain of Qwen agents that write
the screenplay, plan every shot, run a director-critic loop, paint the frames,
turn stills into motion, and record the dialogue — with an approval gate where
you can redraw or reorder any frame before a single video credit is spent.

## Inspiration
AI video is finally good enough to tell a story, but the workflow is backwards:
people render first and fix later, burning the most expensive step over and over.
We wanted a tool that thinks like a real production — lock the script and the
storyboard on paper (cheap), then shoot once (expensive). And we wanted it to
speak the native language of the internet: vertical, voiced, captioned, ready to
post.

## What it does
- **Writes** a short screenplay from one logline (`qwen3.7-max`).
- **Plans** every shot — framing, action, the spoken line, the speaker
  (`qwen3.7-plus`).
- **Critiques the storyboard before rendering** — a director-critic loop scores
  it for continuity, clarity, and AI-renderability and rewrites risky shots
  while it's still text (fractions of a cent per round).
- **Paints** each frame with `qwen-image-2.0-pro`, keeping characters consistent
  via a series bible + cast reference sheets.
- **Approval gate**: you see the full storyboard and can redraw a frame (with a
  director's note), reorder, or drop shots — the script and caption stay in sync.
- **Films** — each approved still becomes the first frame of a HappyHorse
  image-to-video clip (`happyhorse-1.1-i2v`).
- **Voices** every line (`qwen3-tts-flash`, a distinct voice per character) and
  **cuts** the film with crossfades and time-aligned dialogue (ffmpeg).
- **Cost ledger**: every token and API call is recorded to
  `runs/<id>/run_report.json` — the finished film shows exactly what it cost.

## How we built it
A stateful Python service (stdlib HTTP server, no framework) drives a pipeline of
Qwen Cloud models over the DashScope international API. The UI is one glass page:
a ChatGPT-style composer, a live studio view that streams each stage
(script → board → critic → storyboard → film) with skeleton loaders, and a
premiere that presents the result as a TikTok post with a copy-ready caption and
hashtags. The whole thing ships as one container (Python + ffmpeg) on Alibaba
Function Compute.

Two ideas do the heavy lifting:
1. **Critic-before-render.** Video is the costly step, so we converge on the
   storyboard in text first. A ~$0.002 critique round replaces a ~$1 re-render.
2. **Series bible.** The backend composes every shot prompt from verbatim
   character descriptions + a style preset, so the model never re-describes a
   character and faces/outfits stay consistent across shots.

## Token-budget optimization (track criterion, with receipts)
Real ledger from the seeded "Gods of the Pitch" run: the text stages —
screenplay, shot plan, and up to three critic rounds — cost **~1–2 cents total**
and decide everything, so the expensive HappyHorse renders happen once on an
already-approved board. Every run writes its own `run_report.json` line-item log;
the number on the premiere screen is that ledger's total, not an estimate.

## Challenges we ran into
- **Content moderation** on the image model would false-positive on staging like
  "hug" — we rewrite intimate wording into G-rated symbolic staging and, when a
  frame is still blocked, we show it honestly with a reason and a Regenerate
  button rather than faking a fallback.
- **Voice/scene sync** — a line longer than its 5s clip used to spill into the
  next scene; the cut now slows or holds a shot until its line finishes.
- **Character consistency** across shots — solved with the series bible + cast
  reference sheets fed to every frame.

## Accomplishments we're proud of
A one-sentence prompt reliably produces a coherent, voiced, captioned vertical
short for **~$3–7 of compute**, with an honest cost ledger and a human approval
gate — no rendered-then-discarded waste.

## What's next
- Persist user films to NAS and add shareable per-film pages.
- Music/SFX bed and auto-captions burned in as an option.
- A "series" mode: recurring characters across multiple episodes.

## Built with
qwen3.7-max · qwen3.7-plus · qwen-image-2.0-pro · happyhorse-1.1-i2v ·
qwen3-tts-flash · Alibaba Cloud DashScope (Model Studio, intl) · Function Compute ·
Python · ffmpeg

## Links (fill in)
- Live demo: `<FC public URL from DEPLOY.md>`
- Video demo: `<YouTube/Vimeo link>`
- Repo: `<git URL>`
