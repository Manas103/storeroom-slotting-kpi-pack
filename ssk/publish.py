"""Orchestration: builds the full storeroom/demand/slotting pipeline and runs
the oracle-benchmarked travel-distance study.

Kept separate from the scripts in scripts/ so both the benchmark scripts and
the pytest suite build the identical pipeline from one place.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ssk import reference as ref
from ssk.layout import build_bins, coords_lookup
from ssk.demand import generate_materials, generate_picks, assign_pick_lists, material_pick_frequency
from ssk.slotting import compute_required_units, baseline_assignment, reslotted_assignment
from ssk.oracle import optimal_route_distance
from ssk.travel import nearest_neighbor_route_distance


def build_storeroom() -> pd.DataFrame:
    return build_bins(np.random.default_rng(ref.RNG_SEED_LAYOUT))


def build_demand() -> tuple[pd.DataFrame, pd.DataFrame]:
    materials = generate_materials(np.random.default_rng(ref.RNG_SEED_MATERIALS))
    picks = generate_picks(materials, np.random.default_rng(ref.RNG_SEED_PICKS))
    picks = assign_pick_lists(picks, np.random.default_rng(ref.RNG_SEED_PICKS + 1))
    return materials, picks


def build_slotting(bins: pd.DataFrame, materials: pd.DataFrame, picks: pd.DataFrame):
    pick_freq = material_pick_frequency(picks)
    materials_req = compute_required_units(materials, pick_freq)
    baseline = baseline_assignment(bins, materials_req)
    reslotted = reslotted_assignment(bins, materials_req)
    return materials_req, baseline, reslotted


def sample_pick_lists_for_oracle(
    picks: pd.DataFrame, n_samples: int = ref.ORACLE_SAMPLE_SIZE, rng: np.random.Generator | None = None
) -> list[int]:
    """Sample n_samples pick-list ids suitable for the brute-force oracle:
    list size between 2 and PICK_LIST_MAX_SIZE bin-visits (a single-stop list
    has only one possible route and is not an interesting routing sample).
    """
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_ORACLE_SAMPLE)

    sizes = picks.groupby("list_id").size()
    eligible = sizes[sizes >= 2].index.to_numpy()
    n = min(n_samples, len(eligible))
    chosen = rng.choice(eligible, size=n, replace=False)
    return sorted(int(x) for x in chosen)


def route_distances_for_lists(
    picks: pd.DataFrame,
    list_ids: list[int],
    material_to_bin: dict[int, int],
    coords: dict[int, tuple[int, int, int]],
) -> pd.DataFrame:
    """For each list id, compute both the oracle-optimal and the fast
    nearest-neighbor heuristic round-trip distance, under the given
    material-to-bin assignment.
    """
    rows = []
    picks_by_list = picks[picks["list_id"].isin(list_ids)].groupby("list_id")
    for list_id in list_ids:
        group = picks_by_list.get_group(list_id)
        bin_ids = [material_to_bin[m] for m in group["material_id"]]
        coord_list = [coords[b] for b in bin_ids]
        oracle_dist = optimal_route_distance(coord_list)
        heuristic_dist = nearest_neighbor_route_distance(coord_list)
        rows.append(
            {
                "list_id": list_id,
                "n_stops": len(coord_list),
                "n_unique_bins": len(set(bin_ids)),
                "oracle_distance": oracle_dist,
                "heuristic_distance": heuristic_dist,
            }
        )
    return pd.DataFrame(rows)


def travel_benchmark(
    picks: pd.DataFrame,
    bins: pd.DataFrame,
    baseline_assign: dict[int, int],
    reslotted_assign: dict[int, int],
    list_ids: list[int],
) -> dict:
    """The core benchmark: oracle-optimal travel distance under the baseline
    layout vs. under the reslotted layout, on the same sampled pick lists.
    """
    coords = coords_lookup(bins)

    baseline_df = route_distances_for_lists(picks, list_ids, baseline_assign, coords)
    reslotted_df = route_distances_for_lists(picks, list_ids, reslotted_assign, coords)

    merged = baseline_df.merge(
        reslotted_df, on="list_id", suffixes=("_baseline", "_reslotted")
    )

    mean_baseline_oracle = merged["oracle_distance_baseline"].mean()
    mean_reslotted_oracle = merged["oracle_distance_reslotted"].mean()
    pct_reduction = 100.0 * (mean_baseline_oracle - mean_reslotted_oracle) / mean_baseline_oracle

    n_lost = int((merged["oracle_distance_reslotted"] > merged["oracle_distance_baseline"]).sum())

    # Heuristic must never claim a shorter distance than the oracle's true
    # optimum, under either layout.
    heuristic_below_oracle_baseline = int(
        (merged["heuristic_distance_baseline"] < merged["oracle_distance_baseline"] - 1e-6).sum()
    )
    heuristic_below_oracle_reslotted = int(
        (merged["heuristic_distance_reslotted"] < merged["oracle_distance_reslotted"] - 1e-6).sum()
    )

    return {
        "n_lists": len(merged),
        "mean_baseline_oracle_distance": mean_baseline_oracle,
        "mean_reslotted_oracle_distance": mean_reslotted_oracle,
        "pct_reduction": pct_reduction,
        "n_lists_reslotting_lost": n_lost,
        "heuristic_below_oracle_baseline_violations": heuristic_below_oracle_baseline,
        "heuristic_below_oracle_reslotted_violations": heuristic_below_oracle_reslotted,
        "details": merged,
    }
