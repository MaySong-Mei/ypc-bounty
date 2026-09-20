# Theory note

The settlement is a transshipment problem on a payment-compatibility graph.

- Vertex: player.
- Balance `b_i > 0`: receives; `b_i < 0`: pays.
- Directed edge `i -> j`: the pair shares at least one payment rail.
- Flow `x_ij`: cents transferred.
- Support indicator `y_ij = 1[x_ij > 0]`.

The default objective is lexicographic:

1. minimize `max_i sum_j y_ij` (worst active outgoing-payment fanout),
2. minimize `sum_ij y_ij` (total transactions),
3. minimize `sum_ij x_ij` (gross routed amount / relay burden).

For `k = 1`, this is the confluent/support-outdegree-1 structure discussed in the flow literature.
For the practical YPC Venmo/Zelle case, the compatibility graph is the union of two overlapping cliques.
The exact MILP remains the implementation reference because game sizes are small and it naturally extends to extra rails or policy constraints.
