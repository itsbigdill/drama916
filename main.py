"""Showrunner CLI.

  python main.py --smoke                       # verify API key, ~$0.0001
  python main.py "logline here" --dry-run      # full pipeline, $0
  python main.py "logline here"                # real run
"""

import argparse

from dotenv import load_dotenv

load_dotenv()

from showrunner import config                      # noqa: E402
from showrunner.ledger import Ledger               # noqa: E402
from showrunner.llm import chat                    # noqa: E402
from showrunner.pipeline import run                # noqa: E402


def smoke():
    ledger = Ledger()
    reply = chat("smoke", config.MODEL_CHEAP, "Reply with exactly: ok",
                 "ping", ledger)
    print(f"API says: {reply!r} — key works.")
    ledger.print_table()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("logline", nargs="?", help="one-sentence story premise")
    ap.add_argument("--dry-run", action="store_true", help="placeholder clips, $0")
    ap.add_argument("--smoke", action="store_true", help="tiny API check")
    args = ap.parse_args()

    if args.smoke:
        smoke()
    elif args.logline:
        run(args.logline, dry_run=args.dry_run)
    else:
        ap.print_help()
