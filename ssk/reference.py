"""Fixed constants for the simulated storeroom, demand, and inventory model.

Nothing in this file is randomized; every value a module elsewhere in this
package treats as "the" storeroom shape, demand scale, or inventory-policy
parameter is defined once, here, so a script and a test can never silently
disagree about what "4,000 bins" or "90,000 picks" means.
"""

# ---------------------------------------------------------------------------
# Storeroom layout (grid/graph distance model)
# ---------------------------------------------------------------------------
# 20 aisles x 20 bays x 10 shelf levels = 4,000 bins. A bin's physical
# location is the triple (aisle, bay, shelf); aisle and bay index a 2-D floor
# position, shelf indexes vertical height within a bay.
N_AISLES = 20
BAYS_PER_AISLE = 20
SHELVES_PER_BAY = 10
N_BINS = N_AISLES * BAYS_PER_AISLE * SHELVES_PER_BAY  # 4,000

# Rectilinear (Manhattan) distance weights, in feet-equivalent units, for the
# three axes of travel a technician actually performs: walk across to the
# right aisle, walk down the aisle to the right bay, then reach up or down to
# the right shelf level. This is a grid/graph approximation, not a measured
# floor plan; see the README "why a grid distance model" deep-dive for what
# it does and does not capture.
AISLE_SPACING_FT = 12.0
BAY_SPACING_FT = 4.0
SHELF_SPACING_FT = 2.0

# The issue counter / storeroom entrance, the fixed reference point every
# pick list route starts and ends at. Modeled as sitting just outside aisle 0,
# bay 0, ground shelf.
ENTRANCE_AISLE = -1
ENTRANCE_BAY = 0
ENTRANCE_SHELF = 0

# ---------------------------------------------------------------------------
# Bin capacity
# ---------------------------------------------------------------------------
RNG_SEED_LAYOUT = 1001
BIN_CAPACITY_MIN = 50
BIN_CAPACITY_MAX = 3200

# ---------------------------------------------------------------------------
# Materials and demand (measured picks)
# ---------------------------------------------------------------------------
RNG_SEED_MATERIALS = 2002
RNG_SEED_PICKS = 3003
RNG_SEED_INVENTORY = 4004
RNG_SEED_AUDIT = 5005

N_MATERIALS = 3200
N_PICKS = 90_000

# Pick frequency across materials follows a Zipf-like power law so a small
# share of materials accounts for most picks (classic MRO storeroom skew: a
# handful of fast-moving consumables, a long tail of slow-moving spares).
# At N_MATERIALS=3200 this exponent puts roughly 74% of all picks on the
# top 20% of materials by rank, a realistic Pareto skew rather than the
# near-total concentration a higher exponent would produce.
ZIPF_EXPONENT = 0.9

# Pick quantity per line (units pulled in one pick) and simulation window.
PICK_QTY_MIN = 1
PICK_QTY_MAX = 6
SIMULATION_DAYS = 180

# Pick lists (work orders) group individual picks. Sizes are capped so the
# brute-force oracle (see oracle.py) stays tractable: 8! = 40,320
# permutations is the largest single-list cost this pipeline will ever pay.
PICK_LIST_MIN_SIZE = 3
PICK_LIST_MAX_SIZE = 8

# Oracle sample: how many pick lists the brute-force optimal-order solver is
# run against. This is the bounded, independent benchmark the 34% travel
# claim is measured against; see BUILDER standard, "resource courtesy".
ORACLE_SAMPLE_SIZE = 1000
RNG_SEED_ORACLE_SAMPLE = 6006

# ---------------------------------------------------------------------------
# Inventory policy (for the KPI simulation): a simple (s, S) reorder policy
# ---------------------------------------------------------------------------
# Reorder point as a multiple of a material's average daily usage, and
# order-up-to level as a further multiple on top. Lead time is in days.
REORDER_POINT_DAYS_COVER = 4.0
ORDER_UP_TO_DAYS_COVER = 14.0
REPLENISHMENT_LEAD_TIME_DAYS = 3
INITIAL_STOCK_DAYS_COVER = 10.0

# Cycle count audit (drives the inventory-accuracy KPI): fraction of
# material-bins sampled, and the seeded miscount rate used to make the
# simulated audit non-trivial (a real count disagreeing with the system
# figure some of the time, not always matching by construction).
CYCLE_COUNT_SAMPLE_FRACTION = 0.25
CYCLE_COUNT_DISCREPANCY_RATE = 0.06
CYCLE_COUNT_MAX_DISCREPANCY_UNITS = 5

# Dead stock: a material with zero picks across the full simulation window.
DEAD_STOCK_PICK_THRESHOLD = 0

# 5S audit: fraction of bins seeded as missing a physical label, to make the
# missing-label report non-trivial.
LABEL_MISSING_RATE = 0.035
