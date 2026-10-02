"""The brute-force, exhaustive optimal-pick-order solver.

This is the reference oracle the whole travel-distance claim rests on: for a
given set of bin coordinates a pick list must visit, it tries every possible
visiting order and returns the true minimum round-trip distance from the
entrance. It is deliberately slow (O(n!)) and deliberately simple, so its
correctness is obvious by inspection; the fast heuristic in travel.py is
checked against it, never the other way around.

It is never run over anything but a small, explicitly bounded sample
(ORACLE_SAMPLE_SIZE lists, each at most PICK_LIST_MAX_SIZE=8 bins), which is
the entire reason PICK_LIST_MAX_SIZE exists: 8! = 40,320 permutations per
list is the largest single-list cost this module will ever be asked to pay.
"""
from __future__ import annotations

from itertools import permutations

from ssk import reference as ref
from ssk.layout import bin_distance, entrance_distance

MAX_ORACLE_LIST_SIZE = ref.PICK_LIST_MAX_SIZE


def optimal_route_distance(bin_coords: list[tuple[int, int, int]]) -> float:
    """Exact minimum round-trip (entrance -> every bin, in some order -> entrance)
    travel distance, found by trying every permutation of the visiting order.

    Raises ValueError if the list is larger than MAX_ORACLE_LIST_SIZE; callers
    are expected to have already bounded list size at generation time
    (assign_pick_lists in demand.py caps every list at PICK_LIST_MAX_SIZE), so
    hitting this is a sign the bound was bypassed somewhere upstream.
    """
    n = len(bin_coords)
    if n == 0:
        return 0.0
    if n > MAX_ORACLE_LIST_SIZE:
        raise ValueError(
            f"optimal_route_distance: list of {n} bins exceeds the oracle's "
            f"bound of {MAX_ORACLE_LIST_SIZE}; this must be enforced upstream, "
            f"not here, since the oracle is deliberately exhaustive and will "
            f"otherwise try to evaluate {n}! permutations"
        )
    if n == 1:
        return 2.0 * entrance_distance(bin_coords[0])

    # Distinct unique coordinates only matter for order; duplicate bins in a
    # list (two lines picking the same bin) still need every position in the
    # permutation to preserve pick order semantics upstream, so we keep them
    # as given rather than de-duplicating here.
    best = None
    for order in permutations(bin_coords):
        dist = entrance_distance(order[0])
        for a, b in zip(order, order[1:]):
            dist += bin_distance(a, b)
        dist += entrance_distance(order[-1])
        if best is None or dist < best:
            best = dist
    return best
