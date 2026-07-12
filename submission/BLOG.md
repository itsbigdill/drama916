# The $0.02 Film School: how we taught an AI showrunner to think before it spends

*Building drama916 for the Qwen Cloud Global AI Hackathon — a pipeline that turns one sentence into a voiced, vertical, TikTok-ready drama, and the token-budget lesson that shaped every design decision.*

**Live demo:** https://drama916.coralglove.com · **Code:** https://github.com/itsbigdill/drama916

---

Type one sentence:

> *"Ronaldo loses the World Cup and Messi comforts him with cheeseburgers."*

Ten minutes later you're watching a voiced, subtitled-by-speech, 9:16 short film with a copy-ready TikTok caption. That's drama916 — our entry for the **AI Showrunner** track, built entirely on Qwen Cloud.

This post is the honest build journal: the one economic insight the whole architecture hangs on, the character-consistency trick that finally worked, and the deployment potholes we hit running a stateful video pipeline on Alibaba Function Compute.

## The receipt that explains the architecture

Here's the actual cost ledger from one of our showcase films, "Gods of the Pitch" (8 shots, 41 seconds, fully voiced). Every drama916 run writes one of these — `runs/<id>/run_report.json` logs every token, API call, and video-second:

| Stage | Model | Cost |
|---|---|---|
| Screenplay | qwen3.7-max | $0.0122 |
| Shot plan | qwen3.7-plus | $0.0022 |
| **Critic (3 rounds)** | qwen3.7-plus | **$0.0066** |
| Cast sheets | qwen-image-2.0-pro | $0.12 |
| Storyboard stills | qwen-image-2.0-pro | $0.40 |
| Voice (8 lines) | qwen3-tts-flash | $0.016 |
| **Video (8 clips)** | happyhorse-1.1-i2v | **$6.60** |
| **Total** | | **$7.16** |

Look at the shape of that ledger. **All of the thinking — writing, shot planning, three rounds of critique — costs two cents. 0.3% of the film.** The video model is 92%.

So the design rule wrote itself: **iterate where it's free, render once where it's expensive.**

Most generative-video workflows do the opposite. They render, look at the result, wince, and re-render. Every iteration loop passes through the most expensive stage. drama916 moves the whole iteration loop into text:

1. `qwen3.7-max` writes the screenplay (it keeps its extended thinking on — story quality is the one place we pay for depth).
2. `qwen3.7-plus` breaks it into shots: framing, action, emotion, the spoken line, the speaker.
3. A **director-critic loop** (also `qwen3.7-plus`) scores the storyboard 1–10 for continuity, narrative clarity, and — crucially — *AI renderability*: too many characters in frame, complex hand interactions, wording that will trip content moderation. Below 8, it rewrites the risky shots and re-scores. Up to three rounds. Each round costs about **$0.002**.

A critique round is three orders of magnitude cheaper than the re-render it prevents. That's the track's "token budget optimization" criterion, not as a slogan but as a receipt.

## The human gate

Between paper and film there's one more free checkpoint: the storyboard approval gate. All frames are painted with `qwen-image-2.0-pro` (still cheap — $0.40 for a whole board), and the user can redraw any frame with a director's note ("he sits alone on the bench"), reorder shots, or drop them. The note doesn't just repaint the image — a small `qwen3.6-flash` call rewrites the shot's action and, if asked, its spoken line, so the film and its dialogue stay in sync with what you changed.

Only after approval does a single video credit get spent. **Film it** → each approved still becomes the literal first frame of a `happyhorse-1.1-i2v` clip.

## Faces that stay the same: the series bible

Character drift is the classic failure of multi-shot generation — your hero changes shirt, face, and species between shots 2 and 3. Prompt engineering per-shot never fixed it for us. What fixed it was an ownership rule we call the **series bible**:

> The backend owns every character's appearance. The models never re-describe it.

The screenwriter defines each character's `visual` once. The shot planner is *forbidden* from describing appearance — it returns structure only (who's present, what happens, the camera). The backend then composes every image prompt mechanically: style preset + each present character's visual, verbatim + location + action. Add a generated reference portrait per character (painted in the same style preset, passed to every frame), and the strawberry in shot 1 is the strawberry in shot 8.

One honest caveat we learned the hard way: hybrid characters with ambiguous anatomy ("upper body human-like spider") still wobble — the model resolves the ambiguity differently per shot. Visually unambiguous casts hold perfectly.

## No fallbacks, on purpose

Image moderation sometimes blocks a frame ("embrace" is riskier than you'd think). Early versions quietly substituted a neighboring still. We ripped that out. A blocked frame now shows up in the storyboard as *blocked, with the reason*, and a Regenerate button — and the film cannot be shot until every frame is honestly present. A sanitizer rewrites intimate wording into G-rated symbolic staging ("leaning heads together, hearts floating"), which resolves most blocks in one click.

The same honesty applies to voice: when TTS produced a 6.3-second line for a 5.2-second clip, lines started overlapping the next scene. The cut now stretches a shot to hold until its line lands — slow-motion up to 1.6× (reads as a dramatic beat), then a held frame — and the crossfade offsets follow. Films got 5% longer and 100% more intelligible.

## Deploying a stateful video pipeline on Function Compute

The backend is one Python process: stdlib HTTP server, an in-memory run state the UI polls, ffmpeg for the cut. Getting that onto Alibaba Function Compute taught us four things worth writing down:

- **Skip the container registry entirely.** FC custom containers only pull from ACR; instead we ship a zip Web Function — vendored `manylinux2014_x86_64` wheels, a static ffmpeg binary, and a `bootstrap` script — uploaded via OSS (the package is 130MB, over FC's direct-upload limit).
- **Cross-version vendoring bites silently.** We vendor deps on a Python 3.14 machine for a 3.10 runtime. pip evaluates environment markers against the *build* interpreter, so `anyio`'s `exceptiongroup; python_version < "3.11"` dependency was skipped — and the function crashed on import. Pin your backports explicitly.
- **The code directory is read-only.** Only `/tmp` is writable, so the runs directory is env-driven (`RUNS_DIR=/tmp/runs`) and the bootstrap seeds it with showcase films baked into the package.
- **`*.fcapp.run` force-downloads HTML** (`Content-Disposition: attachment` — an anti-phishing measure). A custom domain through Cloudflare (CNAME, SSL mode Full) fixes it; verify the CNAME with the proxy off, then turn the proxy back on for HTTPS.

One config choice matters more than all of these: **minimum instances = 1**. The run state lives in memory; a scale-to-zero recycle mid-render would eat a $7 film. One always-warm instance is the entire "database".

## What we'd do next

Persist user films to OSS (today they live in `/tmp` and survive only as long as the warm instance), a music bed, and a series mode — recurring characters across episodes, which the series bible already makes possible.

## The numbers, one more time

- **1 sentence in → ~41s voiced vertical film out**, ~10 minutes wall-clock
- **$7.16 total**, of which story iteration — the part you want to redo freely — is **$0.02**
- 5 Qwen Cloud models doing distinct jobs: `qwen3.7-max` (writer), `qwen3.7-plus` (planner + critic), `qwen-image-2.0-pro` (frames), `happyhorse-1.1-i2v` (motion), `qwen3-tts-flash` (voices)
- 0 fallbacks, 1 human gate, every cent itemized

Built by a two-person team for the Qwen Cloud Global AI Hackathon, AI Showrunner track.

*Try it: type one line at https://drama916.coralglove.com — the storyboard is yours to direct before a single video credit is spent.*
