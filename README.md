# Storeroom Slotting, Travel-Distance Study and Inventory KPI Pack

A simulated 4,000-bin storeroom reslotted from 90,000 picks of measured,
Pareto-skewed demand, with mean technician travel per pick list measured
against a brute-force optimal-pick-order oracle on 1,000 sampled lists, six
published inventory KPIs each traceable to the rows behind it, and bin-label
and missing-label reports for a 5S audit. Python, DuckDB, Excel (openpyxl).
Every number below was measured on this machine by running the code in this
repository, not targeted to match a prior claim.

## Why this exists

This is a small version of the slotting and reporting half of a storeroom
reliability program: deciding where a fast-moving material physically sits
relative to the issue counter, proving that decision actually shortens a
technician's walk rather than just asserting it, and publishing the handful
of KPIs a planning meeting actually looks at, each one checkable against the
rows that produced it rather than taken on faith.

## Honest framing

- **All data is synthetic.** The 4,000-bin layout, 3,200 materials, 90,000
  picks, pick lists, and the 180-day inventory simulation are all generated
  by `ssk/layout.py`, `ssk/demand.py`, and `ssk/kpis.py`. There is no real
  storeroom, material, or technician in this repository.
- **Distance is a rectilinear grid model, not a measured floor plan.** A bin
  sits at (aisle, bay, shelf); distance between two bins is Manhattan
  distance (walk to the right aisle, down it to the right bay, up or down to
  the right shelf), stated up front in `ssk/layout.py`. See "why a grid
  distance model" below for what this does and does not capture.
  Pick frequency is **measured, not assumed uniform**: `ssk/demand.py`
  draws a Zipf-distributed pick weight per material (exponent 0.9, putting
  roughly 74% of the 90,000 picks on the top 20% of materials by rank),
  then every KPI and the slotting assignment itself reads the *resulting*
  pick counts and quantities from the generated `picks` table, never the
  underlying weight directly.
- **The reslotting heuristic is one-SKU-per-bin, closest-first by
  frequency**, not a general bin-packing optimizer; see the design
  deep-dive below for the tradeoff this makes.
- **The oracle is exhaustive and genuinely independent of the fast path.**
  `ssk/oracle.py::optimal_route_distance` tries every permutation of a pick
  list's stops (bounded to at most 8 stops, 8! = 40,320 permutations, so a
  1,000-list benchmark stays tractable on a shared machine); the fast
  nearest-neighbor heuristic in `ssk/travel.py` is checked against it, never
  the reverse.
- **Machine and toolchain.** Windows 11 Home (build 26200), 8 physical / 16
  logical cores, Python 3.12.10, DuckDB 1.5.6, pandas 3.0.6, numpy 2.5.3,
  openpyxl 3.1.5, pytest 9.1.1. The benchmark runs single-process,
  single-threaded Python; the oracle's 1,000-list sample is bounded by
  construction (list size capped at 8) specifically so it stays fast on a
  machine that is in use for other work at the same time.

## Architecture

```
ssk/
  reference.py     # every fixed constant: bin/aisle/bay/shelf counts,
                    #   distance weights, material/pick counts, Zipf
                    #   exponent, pick-list size bounds, oracle sample
                    #   size, inventory-policy and cycle-count parameters
  layout.py          # the 4,000-bin grid: coordinates, capacity, and the
                    #   rectilinear distance model
  demand.py            # 3,200 materials with Zipf-skewed pick weights,
                    #   90,000 picks, grouped into pick lists capped at 8
                    #   stops (the oracle's tractability bound)
  slotting.py            # required bin footprint per material (from
                    #   measured demand), the arbitrary baseline
                    #   assignment, and the frequency-priority reslotted
                    #   assignment, both capacity-respecting
  oracle.py                # the exhaustive O(n!) optimal-pick-order solver,
                    #   bounded to lists of at most 8 stops
  travel.py                  # the fast O(n^2) nearest-neighbor heuristic,
                    #   checked against the oracle, never trusted alone
  kpis.py                      # the 180-day (s, S) inventory simulation and
                    #   the six published KPIs, each computed as literal
                    #   DuckDB SQL with its row count as lineage
  audit.py                      # the 5S bin-label and missing-label Excel
                    #   workbook (openpyxl)
  publish.py                      # orchestration: wires the modules above
                    #   into the one pipeline both the benchmark script and
                    #   the test suite build from
scripts/
  run_benchmark.py                 # full end-to-end run; prints every
                    #   number this README reports
tests/
  test_ssk.py                        # capacity invariants, a hand-verifiable
                    #   oracle case, the heuristic-never-beats-oracle
                    #   property over 200 random samples, KPI lineage
                    #   coverage, and the 5S workbook's row accounting
docs/
  benchmark_output.txt                # raw output of scripts/run_benchmark.py
  test_output.txt                      # raw output of pytest -v
artifacts/
  5s_audit.xlsx                          # the committed 5S workbook this
                    #   run produced (121 KB; regenerated by the benchmark
                    #   command, kept here as a small, inspectable sample
                    #   output in the spirit of this portfolio's other
                    #   committed plot/report artifacts)
```

### Design deep-dives

**Why a grid distance model.** A real storeroom floor plan has irregular
aisle widths, cross-aisles, and obstacles; a pure rectilinear grid captures
none of that. What it does capture, honestly, is the one thing the claim
depends on: that walking to a closer bin costs less than walking to a
farther one, monotonically in each axis, which is the property both the
reslotting heuristic and the oracle rely on. The README's Limitations
section states plainly what this does not model.

**One SKU per bin, not general bin-packing.** `slotting.py::_first_fit`
assigns at most one material per bin location, consuming a bin's entire
capacity to place it rather than co-locating several small materials in one
bin. This is a simplification of a real storeroom (which does co-locate
small parts), chosen because it makes the capacity invariant trivially
checkable (`assert_capacity_respected`: one material's required units must
not exceed its bin's capacity) and because it is the correct model for the
claim under test: the travel-distance benefit comes entirely from *which*
bin a material's one location sits in, not from packing density.

**Baseline uses a shuffled bin order, not creation order.** A first cut
might assign bins in `bin_id` (row-major aisle/bay/shelf) order for the
"arbitrary" baseline. `baseline_assignment` deliberately shuffles the bin
order instead (seeded), because row-major order happens to put low aisle
numbers, which are physically closer to the entrance, early in the
sequence; an arbitrary historical slotting has no such correlation, and a
baseline that accidentally favors close-in bins would understate the real
benefit of deliberate reslotting.

**KPI lineage is the literal SQL plus the row count, not a cached number.**
Every function in `kpis.py` returns the exact query string it ran alongside
the value, so a downstream reader can re-run the identical query against
the same tables and get the same number back. `lineage_coverage` checks
this is actually true of every published KPI (nonzero backing rows), not
just asserted.

## Validation

1. **Reference oracle.** `tests/test_ssk.py::test_heuristic_never_beats_the_oracle`
   checks, over 200 randomly sampled small pick lists (not just the
   benchmark's own 1,000-list sample), that the fast nearest-neighbor
   heuristic never reports a distance shorter than the oracle's true
   optimum for the same stops. `test_oracle_hand_verifiable_two_bin_case`
   checks a hand-computable two-bin case exactly. `test_oracle_raises_above_its_bounded_size`
   confirms the oracle refuses a list beyond its tractable bound rather than
   silently running an unbounded factorial search.
2. **Invariants.** Bin-capacity is never exceeded under either assignment
   (`assert_capacity_respected`, checked for both baseline and reslotted);
   every material is placed exactly once; the reslotted assignment measurably
   puts higher-pick-frequency materials closer to the entrance than
   lower-frequency ones (top decile by pick count vs. bottom decile).
3. **KPI lineage.** All six KPIs have nonzero backing rows (100% coverage),
   checked directly against a freshly built pipeline, not the benchmark's
   cached numbers.
4. **5S workbook.** The workbook accounts for every one of the 4,000 bins on
   the "Bin Labels" sheet and the missing-label sheet's row count matches
   the seeded missing count exactly.

Full pytest run (9 tests):

```
$ venv/Scripts/python.exe -m pytest tests -v
...
9 passed in 6.38s
```

Full output: `docs/test_output.txt`.

## Findings: what broke

**Writing an independent test fixture at reduced scale broke the Zipf
pick-weight distribution, and the failure mode is worth recording because
it is a general hazard of truncating a pre-normalized population.** Symptom:
a first draft of the test suite built a "small world" fixture by calling
`generate_materials()` at full scale and then slicing it down to the first
200 rows with `.head(200)` before generating picks, to keep the test suite
fast. Every test depending on that fixture failed at setup with
`ValueError: Probabilities do not sum to 1` inside `numpy.random.Generator.choice`.
Wrong hypothesis: none needed, the traceback pointed directly at
`rng.choice(..., p=materials["pick_weight"])` inside `generate_picks`.
Root cause: `generate_materials` normalizes the Zipf weights by dividing by
the sum **over all 3,200 materials**, so any 200-row subset of that table
carries weights that sum to something less than 1 (whatever fraction of the
total weight happened to survive the slice), and `numpy.random.Generator.choice`
correctly refuses to treat that as a probability distribution. Fix: the test
fixture now generates the full-scale 3,200-material, 90,000-pick population
(still fast, under a second) rather than slicing after generation, with its
own independent seed set distinct from `scripts/run_benchmark.py`'s, so the
test suite is a genuinely separate run, not a replay of the benchmark's
exact numbers. Why it mattered: this is exactly the kind of mistake that
would silently produce a *biased* rather than *failing* small-scale test in
a less careful spot (if the Zipf weights had instead been clipped rather
than divided, the slice might have "worked" while quietly testing a
different, wrong distribution); here it failed loudly instead, which is the
better outcome and the reason the fix is a generation-scale change, not a
workaround that re-normalizes the sliced weights.

**The reslotting heuristic does not uniformly win: 37 of 1,000 sampled pick
lists see a reslotted-layout route longer than the baseline's, for the same
stops.** This is disclosed rather than smoothed over: a frequency-priority,
closest-bin-first assignment optimizes the *population* of pick lists, not
every individual one, since a pick list that happens to combine one very
high-frequency material (now close to the entrance) with several very
low-frequency ones (now, by construction, pushed toward the back to make
room) can end up with a longer best-case route than an arbitrary layout
that, by chance, placed all of that specific list's materials near each
other. See Measured results for the exact count and Limitations for the
broader implication.

## Measured results

Machine: Windows 11 Home (build 26200), 8 physical / 16 logical cores,
Python 3.12.10, single-process, single-threaded. Command:
`venv/Scripts/python.exe scripts/run_benchmark.py`. Full output:
`docs/benchmark_output.txt`.

| metric | claimed | measured | met |
|---|---|---|---|
| simulated storeroom bins | 4,000 | 4,000 | yes |
| picks of measured demand | 90,000 | 90,000 | yes |
| reslotted under bin-capacity limits | yes | yes, both baseline and reslotted assignments checked by `assert_capacity_respected`, 0 violations | yes |
| mean technician travel per pick list, cut vs. baseline, measured against the oracle | 34% | **44.0%** (581.18 ft baseline -> 325.20 ft reslotted, mean oracle-optimal distance over 1,000 sampled pick lists) | yes, exceeded |
| inventory KPIs published | 6 | 6 (inventory_accuracy, fill_rate, availability, consumption_trend, dead_stock, stockout_days) | yes |
| bin-label and missing-label reports for a 5S audit | yes | `artifacts/5s_audit.xlsx`: 4,000 bins, 149 (3.73%) missing a label, filtered worklist sheet | yes |
| each KPI figure traceable to the rows behind it | yes | 100% lineage coverage (6 of 6 KPIs have at least one backing row; every KPI's literal SQL and row count are returned alongside its value) | yes |

**The one number that matters is the 44.0% oracle-measured travel-distance
reduction, because it is the claim the entire pipeline (layout, demand,
slotting, and the independent oracle) exists to support, and it exceeds the
34% claim rather than falling short.** The honest qualifier: 37 of the
1,000 sampled pick lists (3.7%) see the reslotted layout lose to the
baseline for that specific list (see Findings), so "44.0% mean reduction"
describes the population of pick lists, not a guarantee for every one.

The six KPIs, measured once on this machine:

| KPI | value | backing rows |
|---|---|---|
| inventory_accuracy | 94.5% | 800 (cycle-count audit sample, 25% of 3,200 materials) |
| fill_rate | 89.1036% | 54,694 material-days with nonzero requested quantity |
| availability | 94.8498% | 576,000 material-days (3,200 materials x 180 days) |
| consumption_trend | +0.5476% (second half vs. first half of the window) | 90,000 picks |
| dead_stock | 0.2812% of materials | 9 of 3,200 materials had zero picks |
| stockout_days | 29,665 material-days | 29,665 (material, day) rows with zero opening on-hand |

What "stockout_days" measures: the count of (material, day) rows where
on-hand at the start of the day was exactly zero, under the simple (s, S)
reorder policy `kpis.py::simulate_inventory` runs; it does not distinguish
a material that is out of stock because it is dead (never ordered) from one
cycling normally through a reorder, which is a real limitation of reading
this one KPI in isolation rather than alongside dead_stock.

## Building and running

```
# from projects/storeroom-slotting-kpi-pack
"C:\Users\Manas\AppData\Local\Programs\Python\Python312\python.exe" -m venv venv
venv\Scripts\pip install -r requirements.txt

# tests (9 tests, ~6.4s)
venv\Scripts\python.exe -m pytest tests -v

# full benchmark: 4,000 bins, 3,200 materials, 90,000 picks, 1,000-list
# oracle benchmark, 6 KPIs, 5S workbook (~35s)
venv\Scripts\python.exe scripts\run_benchmark.py
```

`artifacts/5s_audit.xlsx` is committed as a small (121 KB) sample output; it
is regenerated by the benchmark command above. `docs/*.txt` are the captured
raw outputs from the commands above, run on this machine.

## Limitations

- The rectilinear grid distance model does not capture a real storeroom's
  irregular aisle widths, cross-aisles, or physical obstacles; it captures
  only the ordering property (closer bins cost less to reach) the claim
  depends on, stated plainly rather than presented as a measured floor plan.
- Slotting is one material per bin location (no co-location of several
  small materials in one bin), which simplifies the capacity invariant at
  the cost of not modeling a real storeroom's packing density.
- The fast nearest-neighbor heuristic is what a real pick-list app would
  generate at full scale; the 44.0% headline number is measured against the
  oracle's *optimal* ordering on both layouts, not against what the
  heuristic itself would actually deliver day to day, which this
  repository does not separately report.
- 37 of 1,000 sampled pick lists see the reslotted layout lose to the
  baseline for that specific list (see Findings); the 44.0% figure is a
  population mean, not a per-list guarantee.
- The (s, S) inventory policy behind the six KPIs uses one fixed reorder
  point and order-up-to multiple for every material, regardless of its
  pick-frequency tier; a real storeroom would likely vary these by
  criticality or velocity class the way this portfolio's
  `criticality-minmax-policy-engine` does for a different population of
  materials.
- The cycle-count sample behind `inventory_accuracy` covers 25% of
  materials on one randomly chosen day each; a material never sampled in
  that 25% contributes nothing to the accuracy figure, which is disclosed
  in the KPI's own lineage note rather than treated as full coverage.
