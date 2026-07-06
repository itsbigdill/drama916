# Showrunner — one prompt in, a finished short drama out

An autonomous AI showrunner for the Qwen Cloud Hackathon (AI Showrunner track): give it a single logline and it writes the screenplay, storyboards the shots, **critiques the storyboard *before* spending a single video credit**, generates every clip with HappyHorse on Qwen Cloud, and cuts the final film with subtitles.

## Why the pre-generation critic matters

Video generation is the expensive step. Most pipelines iterate *after* rendering — burn, look, re-burn. Showrunner runs a director-critic loop over the shot list while it is still text (fractions of a cent per round), and only sends prompts to HappyHorse once the storyboard passes. Every token and API call is recorded in a cost ledger (`runs/<id>/run_report.json`) — this is the track's "token budget optimization" criterion, with receipts.

## Pipeline

```
logline ─► script_agent (qwen3.7-max) ─► shot_planner (qwen3.7-plus)
                 ▲                              │
                 └──── critic loop (≤3 rounds, text-only, cheap) ◄──┘
                                                │ approved shot list
                                    video_gen (happyhorse-1.1-t2v, async tasks)
                                                │ clips/
                                    assemble (ffmpeg concat + burned subtitles)
                                                ▼
                                        runs/<id>/final.mp4
```

## Quickstart (5 minutes)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # paste your DashScope intl API key
python main.py --smoke      # 1 tiny text call, verifies the key
python main.py "A robot janitor on a space station finds a houseplant" --dry-run
# dry-run: full pipeline, placeholder clips, $0 spent
python main.py "..." # real run, respects MAX_BUDGET_USD from config.py
```

Requires `ffmpeg` on PATH (`brew install ffmpeg`).

## Safety rails

- `--dry-run` renders placeholder clips locally — the whole pipeline is testable for $0.
- `MAX_BUDGET_USD` (config.py) hard-stops before any video task if the estimate exceeds it.
- Every stage writes its artifact to `runs/<timestamp>/` so a crashed run resumes without re-spending.

## License

MIT
