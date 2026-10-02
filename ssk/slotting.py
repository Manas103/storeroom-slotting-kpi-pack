"""Baseline and reslotted bin assignment, both respecting bin-capacity limits.

Every material is assigned to exactly one bin. A material's required storage
footprint (required_units) is derived from its measured demand: average daily
usage over the simulation window, times a days-of-cover target, times its
per-unit volume footprint, with a floor so even a dead-stock material still
occupies a minimal shelf position. Both assignment strategies below must
respect each bin's capacity; that is a hard invariant checked in
test_slotting.py, not a goal they are merely encouraged toward.

- Baseline: materials in arbitrary (material_id) order, bins in arbitrary
  (bin_id, i.e. creation / row-major aisle-bay-shelf) order, first bin found
  with enough remaining capacity. This models a storeroom slotted with no
  attention to pick frequency, which is the realistic starting point this
  project claims to improve on.
- Reslotted: materials in descending pick-frequency order, assigned to the
  closest-to-entrance bin (by dist_from_entrance) that still has enough
  capacity. Highest-frequency materials get first pick of the close-in bins.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ssk import reference as ref


def compute_required_units(materials: pd.DataFrame, pick_freq: pd.DataFrame) -> pd.DataFrame:
    """Required bin capacity per material, derived from measured demand.

    A material with zero picks in material_pick_frequency (dead stock) still
    gets a minimal floor requirement: real storerooms keep a minimum stock
    level for a spare part even if it has not moved recently.
    """
    merged = materials.merge(pick_freq, on="material_id", how="left")
    merged["pick_count"] = merged["pick_count"].fillna(0).astype(int)
    merged["total_qty"] = merged["total_qty"].fillna(0).astype(int)

    avg_daily_usage = merged["total_qty"] / ref.SIMULATION_DAYS
    raw_required = np.ceil(avg_daily_usage * ref.ORDER_UP_TO_DAYS_COVER) * merged["unit_footprint"]
    floor = merged["unit_footprint"] * 5
    merged["required_units"] = np.maximum(raw_required, floor).astype(int)
    return merged


def _first_fit(materials_order: list[int], bins_order: list[int], required: dict, capacity: dict):
    """One material per bin: assign each material (in the given order) to
    the first still-unused bin (in the given order) whose capacity is
    sufficient. A bin is consumed in full by the one material placed in it,
    whatever headroom is left over; this is a slotting model (one SKU per
    bin location), not a general bin-packing problem. Returns (assignment
    dict material_id -> bin_id, list of unassigned material_ids).
    """
    assignment: dict[int, int] = {}
    unassigned: list[int] = []
    available = list(bins_order)

    for mat_id in materials_order:
        need = required[mat_id]
        placed = False
        for idx, bin_id in enumerate(available):
            if capacity[bin_id] >= need:
                assignment[mat_id] = bin_id
                available.pop(idx)
                placed = True
                break
        if not placed:
            unassigned.append(mat_id)
    return assignment, unassigned


def baseline_assignment(bins: pd.DataFrame, materials_req: pd.DataFrame, rng: np.random.Generator | None = None) -> dict[int, int]:
    """Arbitrary first-fit assignment: materials in material_id order, bins in
    a fixed random shuffle (seeded), not sorted by distance from the
    entrance. Sorting bins by bin_id (row-major aisle/bay/shelf creation
    order) would accidentally favor low aisle numbers, which happen to sit
    closer to the entrance; a real arbitrary/FCFS historical slotting has no
    such correlation, so a shuffled bin order is the more honest "arbitrary".
    """
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_LAYOUT + 500)

    materials_order = sorted(materials_req["material_id"].tolist())
    bins_order = rng.permutation(bins["bin_id"].to_numpy()).tolist()
    required = dict(zip(materials_req["material_id"], materials_req["required_units"]))
    capacity = dict(zip(bins["bin_id"], bins["capacity"]))

    assignment, unassigned = _first_fit(materials_order, bins_order, required, capacity)
    if unassigned:
        raise RuntimeError(
            f"baseline_assignment: {len(unassigned)} materials could not be placed "
            f"in any bin with sufficient capacity: {unassigned[:10]}..."
        )
    return assignment


def reslotted_assignment(bins: pd.DataFrame, materials_req: pd.DataFrame) -> dict[int, int]:
    """Frequency-priority, closest-bin-first assignment, capacity-respecting."""
    materials_order = (
        materials_req.sort_values(["pick_count", "material_id"], ascending=[False, True])[
            "material_id"
        ].tolist()
    )
    bins_order = bins.sort_values(["dist_from_entrance", "bin_id"])["bin_id"].tolist()
    required = dict(zip(materials_req["material_id"], materials_req["required_units"]))
    capacity = dict(zip(bins["bin_id"], bins["capacity"]))

    assignment, unassigned = _first_fit(materials_order, bins_order, required, capacity)
    if unassigned:
        raise RuntimeError(
            f"reslotted_assignment: {len(unassigned)} materials could not be placed "
            f"in any bin with sufficient capacity: {unassigned[:10]}..."
        )
    return assignment


def assert_capacity_respected(assignment: dict[int, int], bins: pd.DataFrame, materials_req: pd.DataFrame) -> None:
    """Invariant: no bin's assigned material(s) exceed its capacity.

    Each bin holds at most one material in this model, so the check reduces
    to: for every (material, bin) pair, required_units <= bin capacity.
    """
    capacity = dict(zip(bins["bin_id"], bins["capacity"]))
    required = dict(zip(materials_req["material_id"], materials_req["required_units"]))
    bin_occupants: dict[int, list[int]] = {}
    for mat_id, bin_id in assignment.items():
        bin_occupants.setdefault(bin_id, []).append(mat_id)

    for bin_id, occupants in bin_occupants.items():
        if len(occupants) > 1:
            raise AssertionError(f"bin {bin_id} has {len(occupants)} materials assigned, expected at most 1")
        total_required = sum(required[m] for m in occupants)
        if total_required > capacity[bin_id]:
            raise AssertionError(
                f"bin {bin_id} capacity {capacity[bin_id]} exceeded by required {total_required} "
                f"(materials {occupants})"
            )
