from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix, vstack

from .model import Player, SettlementResult, Transfer


class SettlementInfeasible(RuntimeError):
    pass


@dataclass(frozen=True)
class _Arc:
    u: int
    v: int
    rail: str


def _validate_players(players: Sequence[Player]) -> None:
    if not players:
        raise ValueError("At least one player is required")
    names = [p.name for p in players]
    if len(names) != len(set(names)):
        raise ValueError("Player names must be unique after aggregation")
    total = sum(p.balance_cents for p in players)
    if total != 0:
        raise ValueError(f"Balances must sum to $0.00; got {total} cents")


def _build_arcs(players: Sequence[Player]) -> list[_Arc]:
    arcs: list[_Arc] = []
    for i, p in enumerate(players):
        for j, q in enumerate(players):
            if i == j:
                continue
            shared = sorted(p.rails & q.rails)
            if shared:
                # One directed arc per ordered pair. If multiple rails are shared,
                # choose a deterministic representative rail for the human plan.
                arcs.append(_Arc(i, j, shared[0]))
    return arcs


def _connected_balance_precheck(players: Sequence[Player], arcs: Sequence[_Arc]) -> None:
    """Every undirected compatibility component must have zero net balance."""
    n = len(players)
    adj = [[] for _ in range(n)]
    for a in arcs:
        adj[a.u].append(a.v)
        adj[a.v].append(a.u)
    seen = [False] * n
    for start in range(n):
        if seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp: list[int] = []
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
        s = sum(players[i].balance_cents for i in comp)
        if s != 0:
            names = ", ".join(players[i].name for i in comp)
            raise SettlementInfeasible(
                f"Compatibility component [{names}] has non-zero net balance ({s} cents)"
            )


def _make_problem(players: Sequence[Player], arcs: Sequence[_Arc]):
    n = len(players)
    m = len(arcs)
    # Variable layout: [x_0..x_{m-1}, y_0..y_{m-1}, K]
    x0 = 0
    y0 = m
    kidx = 2 * m
    nv = 2 * m + 1

    total_positive = sum(max(0, p.balance_cents) for p in players)
    M = max(1, total_positive)

    rows = []
    lbs = []
    ubs = []

    # Exact flow conservation: inflow - outflow = balance.
    for i, p in enumerate(players):
        row = lil_matrix((1, nv), dtype=float)
        for e, a in enumerate(arcs):
            if a.v == i:
                row[0, x0 + e] += 1
            if a.u == i:
                row[0, x0 + e] -= 1
        rows.append(row)
        lbs.append(float(p.balance_cents))
        ubs.append(float(p.balance_cents))

    # Link x and y: y_e <= x_e <= M*y_e. x is integral cents.
    for e in range(m):
        row_hi = lil_matrix((1, nv), dtype=float)
        row_hi[0, x0 + e] = 1
        row_hi[0, y0 + e] = -M
        rows.append(row_hi)
        lbs.append(-np.inf)
        ubs.append(0.0)

        row_lo = lil_matrix((1, nv), dtype=float)
        row_lo[0, y0 + e] = 1
        row_lo[0, x0 + e] = -1
        rows.append(row_lo)
        lbs.append(-np.inf)
        ubs.append(0.0)

    # Per-node outgoing support degree <= K.
    for i in range(n):
        row = lil_matrix((1, nv), dtype=float)
        for e, a in enumerate(arcs):
            if a.u == i:
                row[0, y0 + e] += 1
        row[0, kidx] = -1
        rows.append(row)
        lbs.append(-np.inf)
        ubs.append(0.0)

    A = vstack(rows, format="csr") if rows else lil_matrix((0, nv)).tocsr()
    lb = np.array(lbs, dtype=float)
    ub = np.array(ubs, dtype=float)

    lower = np.zeros(nv, dtype=float)
    upper = np.empty(nv, dtype=float)
    upper[:m] = M
    upper[m:2 * m] = 1
    upper[kidx] = max(0, n - 1)
    integrality = np.ones(nv, dtype=int)

    return {
        "n": n,
        "m": m,
        "nv": nv,
        "x0": x0,
        "y0": y0,
        "kidx": kidx,
        "A": A,
        "lb": lb,
        "ub": ub,
        "bounds": Bounds(lower, upper),
        "integrality": integrality,
    }


def _solve_stage(problem, c: np.ndarray, extra_rows=None, extra_lb=None, extra_ub=None):
    A = problem["A"]
    lb = problem["lb"]
    ub = problem["ub"]
    if extra_rows:
        A = vstack([A, *extra_rows], format="csr")
        lb = np.concatenate([lb, np.asarray(extra_lb, dtype=float)])
        ub = np.concatenate([ub, np.asarray(extra_ub, dtype=float)])
    result = milp(
        c=c,
        integrality=problem["integrality"],
        bounds=problem["bounds"],
        constraints=LinearConstraint(A, lb, ub),
        options={"presolve": True},
    )
    if not result.success or result.x is None:
        raise SettlementInfeasible(result.message or "No feasible settlement")
    return result.x


def _eq_row(nv: int, indices: Iterable[int], coeff: float = 1.0):
    row = lil_matrix((1, nv), dtype=float)
    for i in indices:
        row[0, i] = coeff
    return row.tocsr()


def _topological_transfer_order(
    players: Sequence[Player], arcs: Sequence[_Arc], flows: Sequence[int]
) -> list[int]:
    """Order positive-flow edges so all incoming transfers to a node happen before its outgoing transfers."""
    n = len(players)
    outgoing: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    support_edges: list[tuple[int, int, int]] = []
    for e, cents in enumerate(flows):
        if cents <= 0:
            continue
        a = arcs[e]
        outgoing[a.u].append(e)
        indeg[a.v] += 1
        support_edges.append((a.u, a.v, e))

    q = deque(i for i in range(n) if indeg[i] == 0)
    node_order: list[int] = []
    indeg_work = indeg[:]
    while q:
        u = q.popleft()
        node_order.append(u)
        for e in outgoing[u]:
            v = arcs[e].v
            indeg_work[v] -= 1
            if indeg_work[v] == 0:
                q.append(v)

    if len(node_order) != n:
        # Gross-flow minimization should eliminate positive cycles, but retain a safe fallback.
        return [e for _, _, e in support_edges]

    ordered: list[int] = []
    for u in node_order:
        ordered.extend(sorted(outgoing[u], key=lambda e: players[arcs[e].v].name))
    return ordered


def solve_settlement(players: Sequence[Player], objective: str = "tail") -> SettlementResult:
    """Solve the YPC settlement problem exactly to the cent.

    objective="tail": lexicographically minimize
      1) maximum outgoing payment count per player,
      2) total transaction count,
      3) gross routed dollars (penalizes unnecessary relays).

    objective="transactions": lexicographically minimize
      1) total transaction count,
      2) maximum outgoing payment count,
      3) gross routed dollars.
    """
    players = tuple(players)
    _validate_players(players)
    arcs = _build_arcs(players)
    _connected_balance_precheck(players, arcs)
    problem = _make_problem(players, arcs)
    m = problem["m"]
    nv = problem["nv"]
    y_indices = list(range(problem["y0"], problem["y0"] + m))
    x_indices = list(range(problem["x0"], problem["x0"] + m))
    kidx = problem["kidx"]

    extra_rows = []
    extra_lb = []
    extra_ub = []

    if objective not in {"tail", "transactions"}:
        raise ValueError("objective must be 'tail' or 'transactions'")

    if objective == "tail":
        c = np.zeros(nv)
        c[kidx] = 1
        sol = _solve_stage(problem, c)
        k_star = int(round(sol[kidx]))
        row = _eq_row(nv, [kidx])
        extra_rows.append(row)
        extra_lb.append(k_star)
        extra_ub.append(k_star)

        c = np.zeros(nv)
        c[y_indices] = 1
        sol = _solve_stage(problem, c, extra_rows, extra_lb, extra_ub)
        e_star = int(round(sum(sol[i] for i in y_indices)))
        row = _eq_row(nv, y_indices)
        extra_rows.append(row)
        extra_lb.append(e_star)
        extra_ub.append(e_star)
    else:
        c = np.zeros(nv)
        c[y_indices] = 1
        sol = _solve_stage(problem, c)
        e_star = int(round(sum(sol[i] for i in y_indices)))
        row = _eq_row(nv, y_indices)
        extra_rows.append(row)
        extra_lb.append(e_star)
        extra_ub.append(e_star)

        c = np.zeros(nv)
        c[kidx] = 1
        sol = _solve_stage(problem, c, extra_rows, extra_lb, extra_ub)
        k_star = int(round(sol[kidx]))
        row = _eq_row(nv, [kidx])
        extra_rows.append(row)
        extra_lb.append(k_star)
        extra_ub.append(k_star)

    # Final tie-break: minimize gross routed amount, which removes pointless relay/cycle flow.
    c = np.zeros(nv)
    c[x_indices] = 1
    sol = _solve_stage(problem, c, extra_rows, extra_lb, extra_ub)

    flows = [int(round(sol[i])) for i in x_indices]
    edge_order = _topological_transfer_order(players, arcs, flows)
    transfers: list[Transfer] = []
    for e in edge_order:
        cents = flows[e]
        if cents <= 0:
            continue
        a = arcs[e]
        transfers.append(
            Transfer(
                sender=players[a.u].name,
                receiver=players[a.v].name,
                cents=cents,
                rail=a.rail,
            )
        )

    outgoing = defaultdict(int)
    for t in transfers:
        outgoing[t.sender] += 1

    return SettlementResult(
        transfers=tuple(transfers),
        max_out_degree=max(outgoing.values(), default=0),
        transaction_count=len(transfers),
        gross_flow_cents=sum(t.cents for t in transfers),
        objective=objective,
    )
