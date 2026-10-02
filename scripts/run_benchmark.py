"""Full end-to-end benchmark: builds the 4,000-bin storeroom, 90,000 picks of
measured demand, baseline and reslotted bin assignments, the oracle-vs-
heuristic travel-distance study on 1,000 sampled pick lists, the six
published KPIs, and the 5S bin-label audit workbook. Prints every number
this repository's README reports.

Usage:
    python scripts/run_benchmark.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ssk import reference as ref
from ssk.publish import (
    build_storeroom, build_demand, build_slotting,
    sample_pick_lists_for_oracle, travel_benchmark,
)
from ssk.kpis import simulate_inventory, generate_cycle_counts, connect, all_kpis, lineage_coverage
from ssk.audit import generate_label_status, write_5s_audit_workbook


def main() -> None:
    t0 = time.time()
    print("=== Storeroom Slotting, Travel-Distance Study and Inventory KPI Pack ===")
    print(f"Bins: {ref.N_BINS}  Materials: {ref.N_MATERIALS}  Picks: {ref.N_PICKS}")
    print()

    bins = build_storeroom()
    materials, picks = build_demand()
    print(f"Generated {len(bins)} bins, {len(materials)} materials, {len(picks)} picks.")

    materials_req, baseline, reslotted = build_slotting(bins, materials, picks)
    print(f"Baseline and reslotted assignments built for {len(materials_req)} materials, "
          f"both respecting each bin's capacity limit.")

    list_ids = sample_pick_lists_for_oracle(picks)
    print(f"Sampled {len(list_ids)} pick lists (size {ref.PICK_LIST_MIN_SIZE}-{ref.PICK_LIST_MAX_SIZE}) "
          f"for the brute-force optimal-pick-order oracle.")

    bench = travel_benchmark(picks, bins, baseline, reslotted, list_ids)
    print()
    print("=== Travel-distance benchmark (oracle-optimal order, mean per pick list) ===")
    print(f"  baseline layout:   {bench['mean_baseline_oracle_distance']:.2f} ft")
    print(f"  reslotted layout:  {bench['mean_reslotted_oracle_distance']:.2f} ft")
    print(f"  reduction: {bench['pct_reduction']:.1f}%")
    print(f"  pick lists where reslotting lost to baseline: {bench['n_lists_reslotting_lost']} of {bench['n_lists']}")
    print(f"  heuristic-below-oracle violations (baseline): {bench['heuristic_below_oracle_baseline_violations']}")
    print(f"  heuristic-below-oracle violations (reslotted): {bench['heuristic_below_oracle_reslotted_violations']}")

    print()
    print("Running 180-day (s, S) inventory simulation for KPI computation...")
    inventory_daily = simulate_inventory(materials_req, picks)
    cycle_counts = generate_cycle_counts(inventory_daily)
    con = connect(bins, materials_req, picks, inventory_daily, cycle_counts)
    results = all_kpis(con)
    print()
    print("=== Six published KPIs ===")
    for r in results:
        print(f"  {r.name}: {r.value} {r.unit}  (lineage rows: {r.lineage_row_count})  {r.note}")
    coverage = lineage_coverage(results)
    print(f"KPI lineage coverage: {coverage:.1f}% ({sum(1 for r in results if r.lineage_row_count > 0)} of {len(results)} KPIs have at least one backing row)")

    print()
    print("Building the 5S bin-label audit workbook...")
    label_status = generate_label_status(bins)
    n_missing = int((label_status["label_status"] == "MISSING").sum())
    artifacts_dir = os.path.join(os.path.dirname(__file__), "..", "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)
    out_path = os.path.join(artifacts_dir, "5s_audit.xlsx")
    write_5s_audit_workbook(label_status, out_path)
    print(f"  {len(label_status)} bins, {n_missing} missing a label ({100.0 * n_missing / len(label_status):.2f}%)")
    print(f"  workbook written: {out_path}")

    print()
    print(f"Total wall time: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
