"""The fast heuristic route: greedy nearest-neighbor from the entrance.

This is the route a technician would actually be guided to walk at full
scale (90,000 picks, tens of thousands of pick lists), where the oracle's
exhaustive search is far too slow to run. It is validated against the
oracle in test_oracle.py: the heuristic must never report a shorter distance
than the oracle's true optimum for the same list, on every list in the
validation sample.
"""
from __future__ import annotations

from ssk import reference as ref
from ssk.layout import bin_distance, entrance_distance


def nearest_neighbor_route_distance(bin_coords: list[tuple[int, int, int]]) -> float:
    """Greedy nearest-neighbor round trip: from the entrance, repeatedly walk
    to the closest not-yet-visited bin, then return to the entrance at the end.

    This is O(n^2) per list (fine at full scale, n is at most 8 by
    construction here but the implementation does not assume that) and is
    not guaranteed optimal; it is the practical routing a pick-list app would
    generate, not the reference answer.
    """
    n = len(bin_coords)
    if n == 0:
        return 0.0

    remaining = list(bin_coords)
    total = 0.0
    pos = (ref.ENTRANCE_AISLE, ref.ENTRANCE_BAY, ref.ENTRANCE_SHELF)

    while remaining:
        nearest_idx = min(range(len(remaining)), key=lambda i: bin_distance(pos, remaining[i]))
        nxt = remaining.pop(nearest_idx)
        total += bin_distance(pos, nxt)
        pos = nxt

    total += entrance_distance(pos)
    return total
