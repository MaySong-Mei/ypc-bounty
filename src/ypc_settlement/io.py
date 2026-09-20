from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .model import Player, dollars_to_cents


def load_csv(path: str | Path) -> list[Player]:
    """Load and globally pool a ledger CSV.

    Required columns:
      name,balance,rails

    Optional `table` is accepted and ignored for the global-pooling solve; multiple
    rows for the same player are summed before optimization.

    `rails` is pipe/comma/semicolon separated, e.g. `venmo|zelle`.
    """
    balances: dict[str, int] = defaultdict(int)
    rails_by_name: dict[str, set[str]] = defaultdict(set)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"name", "balance", "rails"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        for row in reader:
            name = row["name"].strip()
            if not name:
                raise ValueError("Blank player name")
            balances[name] += dollars_to_cents(row["balance"])
            raw = row["rails"].replace(",", "|").replace(";", "|")
            rails_by_name[name].update(r.strip().lower() for r in raw.split("|") if r.strip())

    return [
        Player(name=name, balance_cents=balances[name], rails=frozenset(rails_by_name[name]))
        for name in sorted(balances)
    ]
