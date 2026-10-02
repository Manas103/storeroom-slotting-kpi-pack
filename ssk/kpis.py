"""Inventory simulation and the six published KPIs, each traceable to rows.

A simple (s, S) reorder policy is simulated day by day for every material
over the SIMULATION_DAYS window, producing a daily on-hand table
(inventory_daily). A cycle-count audit sample is drawn against it. All six
KPIs are computed as DuckDB SQL queries over these tables (plus picks and
materials_req), and every KPI's lineage is the literal SQL text plus the
backing row count, so a downstream reader can re-run the query and get the
same number back rather than trust a bare figure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd

from ssk import reference as ref


def simulate_inventory(materials_req: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    """Day-by-day (s, S) inventory simulation for every material.

    Returns one row per (material_id, day) with on_hand_start, requested_qty,
    fulfilled_qty, on_hand_end, and whether a replenishment order was placed
    or received that day.
    """
    days = ref.SIMULATION_DAYS
    # requested quantity per (material, day), zero-filled
    daily_demand = (
        picks.groupby(["material_id", "day"])["qty"].sum().unstack(fill_value=0)
    )
    daily_demand = daily_demand.reindex(columns=range(days), fill_value=0)

    rows = []
    req = materials_req.set_index("material_id")
    for mat_id, mat_row in req.iterrows():
        avg_daily_usage = mat_row["total_qty"] / days
        reorder_point = math.ceil(avg_daily_usage * ref.REORDER_POINT_DAYS_COVER)
        order_up_to = math.ceil(avg_daily_usage * ref.ORDER_UP_TO_DAYS_COVER)
        order_up_to = max(order_up_to, reorder_point + 1, mat_row["unit_footprint"])
        on_hand = math.ceil(avg_daily_usage * ref.INITIAL_STOCK_DAYS_COVER)
        on_hand = max(on_hand, order_up_to)

        demand_row = daily_demand.loc[mat_id].to_numpy() if mat_id in daily_demand.index else np.zeros(days)
        pending_orders: dict[int, int] = {}  # arrival_day -> qty
        order_outstanding = False

        for day in range(days):
            received = pending_orders.pop(day, 0)
            if received:
                on_hand += received
                order_outstanding = False
            on_hand_start = on_hand

            requested = int(demand_row[day])
            fulfilled = min(requested, on_hand)
            on_hand -= fulfilled

            order_placed = False
            if on_hand <= reorder_point and not order_outstanding:
                qty_to_order = order_up_to - on_hand
                if qty_to_order > 0:
                    arrival = day + ref.REPLENISHMENT_LEAD_TIME_DAYS
                    pending_orders[arrival] = pending_orders.get(arrival, 0) + qty_to_order
                    order_outstanding = True
                    order_placed = True

            rows.append(
                (
                    mat_id,
                    day,
                    on_hand_start,
                    requested,
                    fulfilled,
                    on_hand,
                    order_placed,
                    bool(received),
                )
            )

    return pd.DataFrame(
        rows,
        columns=[
            "material_id",
            "day",
            "on_hand_start",
            "requested_qty",
            "fulfilled_qty",
            "on_hand_end",
            "order_placed",
            "replenishment_received",
        ],
    )


def generate_cycle_counts(inventory_daily: pd.DataFrame, rng: np.random.Generator | None = None) -> pd.DataFrame:
    """A simulated 5S-style cycle-count audit: sample material-days, compare
    the system's on_hand figure against a (sometimes deliberately wrong)
    physical count.
    """
    if rng is None:
        rng = np.random.default_rng(ref.RNG_SEED_AUDIT)

    # one count per material, on a randomly chosen day, for a sample of materials
    material_ids = inventory_daily["material_id"].unique()
    n_sample = max(1, int(len(material_ids) * ref.CYCLE_COUNT_SAMPLE_FRACTION))
    sampled_materials = rng.choice(material_ids, size=n_sample, replace=False)

    records = []
    for mat_id in sampled_materials:
        mat_days = inventory_daily[inventory_daily["material_id"] == mat_id]
        count_day = int(rng.integers(0, ref.SIMULATION_DAYS))
        row = mat_days[mat_days["day"] == count_day]
        if row.empty:
            continue
        system_qty = int(row.iloc[0]["on_hand_end"])
        has_discrepancy = rng.random() < ref.CYCLE_COUNT_DISCREPANCY_RATE
        if has_discrepancy:
            delta = rng.integers(1, ref.CYCLE_COUNT_MAX_DISCREPANCY_UNITS + 1)
            sign = rng.choice([-1, 1])
            counted_qty = max(0, system_qty + sign * delta)
        else:
            counted_qty = system_qty
        records.append((mat_id, count_day, system_qty, counted_qty, has_discrepancy))

    return pd.DataFrame(
        records,
        columns=["material_id", "count_day", "system_qty", "counted_qty", "seeded_discrepancy"],
    )


@dataclass
class KpiResult:
    name: str
    value: float
    unit: str
    lineage_query: str
    lineage_row_count: int
    note: str = ""


def connect(
    bins: pd.DataFrame,
    materials_req: pd.DataFrame,
    picks: pd.DataFrame,
    inventory_daily: pd.DataFrame,
    cycle_counts: pd.DataFrame,
) -> duckdb.DuckDBPyConnection:
    """Register every source table in an in-memory DuckDB connection so each
    KPI can be computed, and its lineage reproduced, as literal SQL.
    """
    con = duckdb.connect(database=":memory:")
    con.register("bins", bins)
    con.register("materials_req", materials_req)
    con.register("picks", picks)
    con.register("inventory_daily", inventory_daily)
    con.register("cycle_counts", cycle_counts)
    return con


def kpi_accuracy(con: duckdb.DuckDBPyConnection) -> KpiResult:
    query = """
        SELECT material_id, count_day, system_qty, counted_qty,
               (system_qty = counted_qty) AS matches
        FROM cycle_counts
    """
    rows = con.execute(query).fetchdf()
    value = 100.0 * rows["matches"].mean() if len(rows) else float("nan")
    return KpiResult(
        name="inventory_accuracy",
        value=round(value, 4),
        unit="%",
        lineage_query=query.strip(),
        lineage_row_count=len(rows),
        note=f"cycle-count audit sample: {len(rows)} of {con.execute('SELECT COUNT(*) FROM materials_req').fetchone()[0]} materials",
    )


def kpi_fill_rate(con: duckdb.DuckDBPyConnection) -> KpiResult:
    query = """
        SELECT material_id, day, requested_qty, fulfilled_qty
        FROM inventory_daily
        WHERE requested_qty > 0
    """
    rows = con.execute(query).fetchdf()
    value = 100.0 * rows["fulfilled_qty"].sum() / rows["requested_qty"].sum() if len(rows) else float("nan")
    return KpiResult(
        name="fill_rate",
        value=round(value, 4),
        unit="%",
        lineage_query=query.strip(),
        lineage_row_count=len(rows),
        note="material-days with nonzero requested quantity; fulfilled_qty capped at that day's opening on-hand",
    )


def kpi_availability(con: duckdb.DuckDBPyConnection) -> KpiResult:
    query = """
        SELECT material_id, day, on_hand_start
        FROM inventory_daily
    """
    rows = con.execute(query).fetchdf()
    value = 100.0 * (rows["on_hand_start"] > 0).mean() if len(rows) else float("nan")
    return KpiResult(
        name="availability",
        value=round(value, 4),
        unit="%",
        lineage_query=query.strip(),
        lineage_row_count=len(rows),
        note="share of material-days where on-hand at day start was greater than zero",
    )


def kpi_consumption_trend(con: duckdb.DuckDBPyConnection) -> KpiResult:
    midpoint = ref.SIMULATION_DAYS // 2
    query = f"""
        SELECT
            SUM(CASE WHEN day < {midpoint} THEN qty ELSE 0 END) AS first_half_qty,
            SUM(CASE WHEN day >= {midpoint} THEN qty ELSE 0 END) AS second_half_qty,
            COUNT(*) AS n
        FROM picks
    """
    row = con.execute(query).fetchdf().iloc[0]
    first_half, second_half, n = row["first_half_qty"], row["second_half_qty"], int(row["n"])
    value = 100.0 * (second_half - first_half) / first_half if first_half else float("nan")
    return KpiResult(
        name="consumption_trend",
        value=round(value, 4),
        unit="% change, first half vs second half of window",
        lineage_query=query.strip(),
        lineage_row_count=n,
        note=f"first-half total qty={int(first_half)}, second-half total qty={int(second_half)}",
    )


def kpi_dead_stock(con: duckdb.DuckDBPyConnection) -> KpiResult:
    query = f"""
        SELECT material_id, pick_count
        FROM materials_req
        WHERE pick_count <= {ref.DEAD_STOCK_PICK_THRESHOLD}
    """
    rows = con.execute(query).fetchdf()
    total = con.execute("SELECT COUNT(*) FROM materials_req").fetchone()[0]
    value = 100.0 * len(rows) / total if total else float("nan")
    return KpiResult(
        name="dead_stock",
        value=round(value, 4),
        unit="% of materials",
        lineage_query=query.strip(),
        lineage_row_count=len(rows),
        note=f"{len(rows)} of {total} materials had zero picks across the {ref.SIMULATION_DAYS}-day window",
    )


def kpi_stockout_days(con: duckdb.DuckDBPyConnection) -> KpiResult:
    query = """
        SELECT material_id, day, on_hand_start
        FROM inventory_daily
        WHERE on_hand_start = 0
    """
    rows = con.execute(query).fetchdf()
    return KpiResult(
        name="stockout_days",
        value=float(len(rows)),
        unit="material-days",
        lineage_query=query.strip(),
        lineage_row_count=len(rows),
        note="count of (material, day) rows where on-hand at day start was exactly zero",
    )


def all_kpis(con: duckdb.DuckDBPyConnection) -> list[KpiResult]:
    return [
        kpi_accuracy(con),
        kpi_fill_rate(con),
        kpi_availability(con),
        kpi_consumption_trend(con),
        kpi_dead_stock(con),
        kpi_stockout_days(con),
    ]


def lineage_coverage(results: list[KpiResult]) -> float:
    """Fraction of published KPIs whose lineage query ran and returned at
    least one backing row. A KPI with zero backing rows would be a coverage
    gap; this returns the honest fraction rather than assuming 100%.
    """
    if not results:
        return 0.0
    covered = sum(1 for r in results if r.lineage_row_count > 0)
    return 100.0 * covered / len(results)
