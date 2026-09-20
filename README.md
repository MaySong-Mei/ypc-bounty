# YPC Settlement

Exact settlement optimizer for YPC cash-game ledgers with Venmo/Zelle (or arbitrary payment-rail) compatibility.

The core UX goal is **not just minimum transaction count**. The default objective minimizes the worst number of active outgoing payments any player has to make, then minimizes total transactions, then minimizes gross routed cash.

## What it does

Given a ledger like:

```csv
name,balance,rails
Alice,-100.00,venmo
Bob,30.00,venmo|zelle
Carol,30.00,zelle
David,40.00,venmo|zelle
```

it finds an exact-to-the-cent settlement subject to payment compatibility.

Positive balance means the player should receive money; negative means the player should pay.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run

```bash
ypc-settle examples/ledger.csv
```

or:

```bash
python -m ypc_settlement.cli examples/ledger.csv --objective tail
```

JSON output:

```bash
ypc-settle examples/ledger.csv --json
```

## Objectives

### `tail` (default)
Lexicographically minimize:

1. maximum outgoing payment count for any player;
2. total transaction count;
3. gross routed amount.

This directly targets the annoying case where one loser has to send many separate payments.

### `transactions`
Lexicographically minimize:

1. total transaction count;
2. maximum outgoing payment count;
3. gross routed amount.

Use this if YPC confirms that “minimize cash flow” really means “fewest total transfers.”

## Model

For each feasible directed payment edge `(i,j)`:

- integer cents `x_ij >= 0`;
- binary support variable `y_ij`;
- `x_ij <= M y_ij`.

Balance conservation:

`inflow_i - outflow_i = b_i`.

Tail variable `K`:

`sum_j y_ij <= K` for every player.

The solver is an exact MILP using `scipy.optimize.milp` / HiGHS. For YPC-sized games this is intentionally simpler and safer than custom heuristics, and it extends directly to 3+ payment methods.

## Multi-table ledgers

Multiple rows with the same player name are automatically pooled before settlement. An optional `table` column is accepted; global pooling nets a player's wins and losses across tables before routing money.

## Correctness / execution

The final gross-flow tie-break removes pointless positive-flow cycles. The CLI emits transfers in a topological order when the support is acyclic, so relay players receive upstream funds before forwarding them.

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```

Tests cover:

- one payer / many receivers;
- one dual-rail bridge where fanout 2 is unavoidable;
- two dual-rail players where one-shot settlement is achievable;
- disconnected incompatible payment components;
- alternate transaction-count-first objective.

## Next YPC validation step

Before freezing the production objective, confirm what YPC means by **“minimize cash flow”**:

- fewest total transactions;
- fewest outgoing actions per payer;
- least money routed through intermediaries;
- or a weighted combination.

The solver already exposes the first two policies and uses gross routed amount as a final tie-break.
