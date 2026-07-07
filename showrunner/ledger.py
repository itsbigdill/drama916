"""Cost/token ledger — the judges' evidence for token budget optimization.

Every model call in the run lands here; run_report.json ships with the repo
so reviewers can see exactly where tokens went and what the critic loop saved.
"""

import json
import time
from dataclasses import asdict, dataclass, field

from rich.console import Console
from rich.table import Table

# intl $/1M tokens (in, out), July 2026 list w/ current promo for max
_TEXT_RATES = {"qwen3.7-max": (1.25, 3.75), "qwen3.7-plus": (0.40, 1.60), "qwen3.6-flash": (0.05, 0.40)}


@dataclass
class Entry:
    stage: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    clips: int = 0
    cost_usd: float = 0.0
    ts: float = field(default_factory=time.time)


class Ledger:
    def __init__(self):
        self.entries: list[Entry] = []

    def record(self, stage, model, tokens_in=0, tokens_out=0, clips=0, clip_cost=0.0):
        rate_in, rate_out = _TEXT_RATES.get(model, (0.0, 0.0))
        cost = tokens_in / 1e6 * rate_in + tokens_out / 1e6 * rate_out + clips * clip_cost
        self.entries.append(Entry(stage, model, tokens_in, tokens_out, clips, round(cost, 5)))

    @property
    def total_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries), 4)

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump({"total_usd": self.total_usd,
                       "entries": [asdict(e) for e in self.entries]}, f, indent=2)

    def print_table(self):
        t = Table(title=f"Run cost: ${self.total_usd}")
        for col in ("stage", "model", "in", "out", "clips", "$"):
            t.add_column(col)
        for e in self.entries:
            t.add_row(e.stage, e.model, str(e.tokens_in), str(e.tokens_out),
                      str(e.clips), f"{e.cost_usd:.4f}")
        Console().print(t)
