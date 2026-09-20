from ypc_settlement import Player, SettlementInfeasible, solve_settlement


def P(name, dollars, rails):
    return Player.from_values(name, dollars, rails)


def assert_balances(players, result):
    net = {p.name: 0 for p in players}
    for t in result.transfers:
        net[t.sender] -= t.cents
        net[t.receiver] += t.cents
    assert net == {p.name: p.balance_cents for p in players}


def test_complete_graph_tail_builds_one_shot_chain():
    players = [
        P("A", -100, ["venmo"]),
        P("B", 30, ["venmo"]),
        P("C", 30, ["venmo"]),
        P("D", 40, ["venmo"]),
    ]
    r = solve_settlement(players, "tail")
    assert r.max_out_degree == 1
    assert r.transaction_count == 3
    assert_balances(players, r)


def test_one_dual_bridge_both_sides_receiving_forces_fanout_two():
    players = [
        P("V", 5, ["venmo"]),
        P("Z", 5, ["zelle"]),
        P("D", -10, ["venmo", "zelle"]),
    ]
    r = solve_settlement(players, "tail")
    assert r.max_out_degree == 2
    assert r.transaction_count == 2
    assert_balances(players, r)


def test_two_dual_players_allow_one_shot():
    players = [
        P("V1", -8, ["venmo"]),
        P("Z1", -2, ["zelle"]),
        P("V2", 3, ["venmo"]),
        P("Z2", 4, ["zelle"]),
        P("D1", 1, ["venmo", "zelle"]),
        P("D2", 2, ["venmo", "zelle"]),
    ]
    r = solve_settlement(players, "tail")
    assert r.max_out_degree == 1
    assert_balances(players, r)


def test_disconnected_imbalanced_components_are_infeasible():
    players = [
        P("V", -5, ["venmo"]),
        P("Z", 5, ["zelle"]),
    ]
    try:
        solve_settlement(players, "tail")
        assert False, "expected infeasible"
    except SettlementInfeasible:
        pass


def test_transaction_objective_prefers_direct_star():
    players = [
        P("A", -100, ["venmo"]),
        P("B", 30, ["venmo"]),
        P("C", 30, ["venmo"]),
        P("D", 40, ["venmo"]),
    ]
    r = solve_settlement(players, "transactions")
    assert r.transaction_count == 3
    # Three edges are information-theoretically necessary for four nonzero balances;
    # the secondary objective may still achieve max fanout 1 via a chain.
    assert r.max_out_degree == 1
    assert_balances(players, r)
