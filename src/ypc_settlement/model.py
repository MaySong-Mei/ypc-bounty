from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


def dollars_to_cents(value: str | int | float | Decimal) -> int:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)


def cents_to_dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100}.{cents % 100:02d}"


@dataclass(frozen=True)
class Player:
    name: str
    balance_cents: int
    rails: frozenset[str]

    @staticmethod
    def from_values(name: str, balance: str | int | float | Decimal, rails: Iterable[str]) -> "Player":
        cleaned = frozenset(r.strip().lower() for r in rails if r.strip())
        if not cleaned:
            raise ValueError(f"{name}: at least one payment rail is required")
        return Player(name=name.strip(), balance_cents=dollars_to_cents(balance), rails=cleaned)


@dataclass(frozen=True)
class Transfer:
    sender: str
    receiver: str
    cents: int
    rail: str


@dataclass(frozen=True)
class SettlementResult:
    transfers: tuple[Transfer, ...]
    max_out_degree: int
    transaction_count: int
    gross_flow_cents: int
    objective: str

    def outgoing_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.transfers:
            counts[t.sender] = counts.get(t.sender, 0) + 1
        return counts
