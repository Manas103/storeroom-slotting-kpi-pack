"""The 4,000-bin storeroom: coordinates, capacity, and the distance model.

The storeroom is a grid: aisle x bay x shelf. Distance between two points is
rectilinear (Manhattan), not Euclidean, because a technician walking a
storeroom floor cannot cut diagonally through a rack; they walk to the right
aisle, walk down it to the right bay, then reach to the right shelf level.
This is documented up front as a simplification, not a measured floor plan;
see the README for what it does not capture.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ssk import reference as ref


def build_bins(rng: np.random.Generator | None = None) -> pd.DataFrame:
    """Build the N_BINS-row bin table: id, coordinates, capacity, distance
    from the entrance.

    Every bin's capacity is drawn independently; nothing here depends on
    which materials will later be assigned to it, so the layout itself
    carries no bias toward the reslotting heuristic that will be measured
    against it.
    """
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_LAYOUT)

    aisles = np.repeat(np.arange(ref.N_AISLES), ref.BAYS_PER_AISLE * ref.SHELVES_PER_BAY)
    bays = np.tile(np.repeat(np.arange(ref.BAYS_PER_AISLE), ref.SHELVES_PER_BAY), ref.N_AISLES)
    shelves = np.tile(np.arange(ref.SHELVES_PER_BAY), ref.N_AISLES * ref.BAYS_PER_AISLE)

    n = len(aisles)
    assert n == ref.N_BINS

    capacity = rng.integers(ref.BIN_CAPACITY_MIN, ref.BIN_CAPACITY_MAX + 1, size=n)

    df = pd.DataFrame(
        {
            "bin_id": np.arange(n),
            "aisle": aisles,
            "bay": bays,
            "shelf": shelves,
            "capacity": capacity,
        }
    )
    df["dist_from_entrance"] = distance_from_entrance(df["aisle"], df["bay"], df["shelf"])
    return df


def distance_from_entrance(aisle, bay, shelf):
    """Rectilinear distance from the issue counter / entrance to (aisle, bay, shelf)."""
    return (
        np.abs(aisle - ref.ENTRANCE_AISLE) * ref.AISLE_SPACING_FT
        + np.abs(bay - ref.ENTRANCE_BAY) * ref.BAY_SPACING_FT
        + np.abs(shelf - ref.ENTRANCE_SHELF) * ref.SHELF_SPACING_FT
    )


def bin_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Rectilinear distance between two (aisle, bay, shelf) coordinates."""
    return (
        abs(a[0] - b[0]) * ref.AISLE_SPACING_FT
        + abs(a[1] - b[1]) * ref.BAY_SPACING_FT
        + abs(a[2] - b[2]) * ref.SHELF_SPACING_FT
    )


def entrance_distance(a: tuple[int, int, int]) -> float:
    """Rectilinear distance between a bin coordinate and the entrance."""
    return bin_distance(a, (ref.ENTRANCE_AISLE, ref.ENTRANCE_BAY, ref.ENTRANCE_SHELF))


def coords_lookup(bins_df: pd.DataFrame) -> dict[int, tuple[int, int, int]]:
    """bin_id -> (aisle, bay, shelf) lookup used by the routing and oracle modules."""
    return {
        int(row.bin_id): (int(row.aisle), int(row.bay), int(row.shelf))
        for row in bins_df.itertuples()
    }
