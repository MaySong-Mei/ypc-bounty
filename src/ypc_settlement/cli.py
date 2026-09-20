from __future__ import annotations

import argparse
import json

from .io import load_csv
from .model import cents_to_dollars
from .solver import SettlementInfeasible, solve_settlement


def main() -> None:
    p = argparse.ArgumentParser(description="YPC payment-rail-aware poker settlement optimizer")
    p.add_argument("ledger", help="CSV with name,balance,rails columns")
    p.add_argument(
        "--objective",
        choices=["tail", "transactions"],
        default="tail",
        help="tail = minimize worst payer fanout first; transactions = minimize transaction count first",
    )
    p.add_argument("--json", action="store_true", dest="as_json")
    args = p.parse_args()

    try:
        players = load_csv(args.ledger)
        result = solve_settlement(players, objective=args.objective)
    except (ValueError, SettlementInfeasible) as e:
        raise SystemExit(f"error: {e}")

    if args.as_json:
        print(
            json.dumps(
                {
                    "objective": result.objective,
                    "max_outgoing_payments_per_person": result.max_out_degree,
                    "transaction_count": result.transaction_count,
                    "gross_routed_cents": result.gross_flow_cents,
                    "transfers": [
                        {
                            "sender": t.sender,
                            "receiver": t.receiver,
                            "amount_cents": t.cents,
                            "rail": t.rail,
                        }
                        for t in result.transfers
                    ],
                },
                indent=2,
            )
        )
        return

    print(f"Objective: {result.objective}")
    print(f"Max outgoing payments/person: {result.max_out_degree}")
    print(f"Transactions: {result.transaction_count}")
    print(f"Gross routed amount: {cents_to_dollars(result.gross_flow_cents)}")
    print("\nSettlement order:")
    if not result.transfers:
        print("  Already settled.")
    for i, t in enumerate(result.transfers, 1):
        print(f"  {i}. {t.sender} -> {t.receiver} via {t.rail}: {cents_to_dollars(t.cents)}")


if __name__ == "__main__":
    main()
