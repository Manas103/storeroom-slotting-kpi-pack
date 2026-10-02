"""Materials and 90,000 picks of measured demand, with a Pareto-ish skew.

Pick frequency is not uniform across materials: a small share of materials
(fast-moving consumables) accounts for most of the 90,000 picks, and a long
tail of materials is picked rarely or never. That skew is exactly what
slotting optimizes against (put the frequently picked materials close to the
entrance) and exactly what later produces genuine dead stock (a material
with zero picks in the window) without having to force it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ssk import reference as ref


def generate_materials(rng: np.random.Generator | None = None) -> pd.DataFrame:
    """N_MATERIALS materials with a Zipf-distributed pick-frequency weight."""
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_MATERIALS)

    n = ref.N_MATERIALS
    # Shuffle the rank-to-material assignment so "high frequency" does not
    # correlate with material_id order, which would make later joins
    # artificially convenient.
    ranks = rng.permutation(n) + 1  # 1-indexed Zipf rank per material
    weights = ranks.astype(float) ** (-ref.ZIPF_EXPONENT)
    weights = weights / weights.sum()

    # A material's physical footprint (units per bin-slot) drives how much
    # bin capacity it needs; independent of pick frequency by design (a
    # fast-moving material is not necessarily bulky).
    unit_footprint = rng.integers(1, 4, size=n)

    return pd.DataFrame(
        {
            "material_id": np.arange(n),
            "zipf_rank": ranks,
            "pick_weight": weights,
            "unit_footprint": unit_footprint,
        }
    )


def generate_picks(materials: pd.DataFrame, rng: np.random.Generator | None = None) -> pd.DataFrame:
    """N_PICKS individual pick lines: material, quantity, simulated timestamp."""
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_PICKS)

    n = ref.N_PICKS
    material_ids = rng.choice(
        materials["material_id"].to_numpy(),
        size=n,
        p=materials["pick_weight"].to_numpy(),
        replace=True,
    )
    qty = rng.integers(ref.PICK_QTY_MIN, ref.PICK_QTY_MAX + 1, size=n)

    # Spread picks across the simulation window; a day plus a fractional
    # time-of-day so picks on the same day still have a strict order.
    day = rng.integers(0, ref.SIMULATION_DAYS, size=n)
    time_of_day = rng.random(n)
    timestamp = day + time_of_day

    df = pd.DataFrame(
        {
            "pick_id": np.arange(n),
            "material_id": material_ids,
            "qty": qty,
            "day": day,
            "timestamp": timestamp,
        }
    )
    return df.sort_values("timestamp").reset_index(drop=True)


def assign_pick_lists(picks: pd.DataFrame, rng: np.random.Generator | None = None) -> pd.DataFrame:
    """Group chronologically sorted picks into pick lists (work orders).

    List sizes are random integers in [PICK_LIST_MIN_SIZE, PICK_LIST_MAX_SIZE].
    The cap at PICK_LIST_MAX_SIZE (8) is deliberate: it bounds the brute-force
    oracle in oracle.py to at most 8! = 40,320 permutations per list, which is
    what keeps a 1,000-list oracle benchmark tractable on a shared machine.
    """
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_PICKS + 1)

    picks = picks.sort_values("timestamp").reset_index(drop=True)
    n = len(picks)
    list_ids = np.empty(n, dtype=np.int64)

    i = 0
    list_id = 0
    while i < n:
        size = rng.integers(ref.PICK_LIST_MIN_SIZE, ref.PICK_LIST_MAX_SIZE + 1)
        size = min(size, n - i)
        list_ids[i : i + size] = list_id
        i += size
        list_id += 1

    picks = picks.copy()
    picks["list_id"] = list_ids
    return picks


def material_pick_frequency(picks: pd.DataFrame) -> pd.DataFrame:
    """Total pick count and total quantity picked per material, over the full window.

    This is the "measured demand" slotting and the inventory simulation both
    read from; materials with zero rows here after a left join are the dead
    stock candidates (see kpis.py).
    """
    agg = (
        picks.groupby("material_id")
        .agg(pick_count=("pick_id", "count"), total_qty=("qty", "sum"))
        .reset_index()
    )
    return agg
