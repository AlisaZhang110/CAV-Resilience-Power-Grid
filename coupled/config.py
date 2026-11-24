"""
config.py -- every assumption of the coupled power-transportation simulation, in one place.

Tags (same convention as traffic/v3 and grid/):
  [DOC]        Failure Mode Table (data/Failure_Mode_Table.xlsx) or Project #4 notes
  [DATA]       computed from a public dataset
  [SRC]        an outside source named next to the value (see coupled/README.md, "Sources")
  [USER]       task spec from Alisa
  [ASSUMPTION] chosen for this prototype; state it as such in any write-up
  GAP          no defensible source yet
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "grid"))
sys.path.insert(0, os.path.join(ROOT, "traffic", "v3_time_of_day"))

from grid_layer import params as GP  # noqa: E402

# ---------------------------------------------------------------------------
# 1. Depots
# ---------------------------------------------------------------------------
EXISTING_DEPOTS = (1, 2, 4, 5)        # [USER] the four marked depots (notes p.5), treated as already built
CANDIDATE_SITES = (3, 6, 7, 8, 9, 10)  # [USER] "one more depot in one of the other locations"
PORTS_PER_DEPOT = 2                   # [ASSUMPTION] model ports per depot (same as the v3 README example)
PORT_MW = 0.108                       # [DOC] 1.8 kWh/min per charger = 108 kW (notes "Waymo Number Breakdown")
DEPOT_RATED_MW = PORTS_PER_DEPOT * PORT_MW

# ---------------------------------------------------------------------------
# 2. Road node <-> feeder bus  (the depot<->bus table the README asked for)
# Every road node gets a bus, not only depot nodes, because the bus also feeds that
# neighbourhood's traffic signals. [ASSUMPTION] The IEEE 33-bus feeder has no geography;
# the mapping puts nodes that share a real hazard exposure on the matching placeholder zone:
#   WUI zone (buses 18-21, 29-32): Santa Monica (Palisades / Santa Monica Mtns edge),
#       Hollywood (Hollywood Hills), Pasadena (San Gabriel foothills / Eaton) -> 3 nodes,
#       which also matches row 12's ">= 3 nodes" PSPS definition.
#   Floodplain (buses 22-24, Ballona Creek): Culver City (500-yr), Playa del Rey (100-yr).
#   Trunk / main feeder: Sawtelle, Downtown (near the substation, strong), West Hollywood,
#       Mid-City (mid-feeder, weaker), LAX (lower lateral).
# ---------------------------------------------------------------------------
NODE_BUS = {1: 21, 2: 3, 3: 7, 4: 26, 5: 22, 6: 2, 7: 23, 8: 10, 9: 29, 10: 32}

# The grid layer reads params.DEPOTS. Every site is attached as a (possibly 0-MW) load so one
# Feeder object serves every placement; an unbuilt site simply demands 0 MW.
GP.DEPOTS.clear()
for _n, _b in NODE_BUS.items():
    GP.DEPOTS[f"N{_n}"] = dict(bus=_b, rated_mw=DEPOT_RATED_MW, road_node=_n)

# ---------------------------------------------------------------------------
# 3. Road-side hazard zones  [ASSUMPTION: tagged by the corridor each edge stands for]
# ---------------------------------------------------------------------------
WUI_EDGES = [(3, 9), (8, 9), (9, 10), (6, 10)]   # Hollywood Hills / Cahuenga / Arroyo Seco / SR-134
#   Row 13 lists 4 applicable WUI edges [DOC]; these are the 4 edges touching the hill nodes.
FLOOD100_EDGES = [(1, 7)]                        # Lincoln Blvd across the Ballona wetlands; row 15: 1 SFHA edge [DOC]
FLOOD500_EDGES = [(1, 7), (5, 7), (1, 5)]        # + SR-90 and Venice/Washington along Ballona Creek

# ---------------------------------------------------------------------------
# 4. Dark traffic signals (grid -> traffic coupling)
# A dark signal is legally an all-way stop [SRC: Toronto / ODOT / Jefferson Co. guidance].
#   Signalized lane capacity ~ 1,900 veh/h of green x g/C (~0.45) ~ 850 veh/h/lane [SRC: HCM, NCHRP 6339].
#   All-way stop TOTAL intersection capacity 400-1,400 veh/h, up to ~1,900 [SRC: Al-Kaisy & Doruk 2023].
#   For two 2-lane-per-direction arterials (~6,800 veh/h signalized) that is ~0.2-0.3; with turn
#   bays and officers at major nodes, use 0.40 for arterial edges [ASSUMPTION within that range].
#   Freeway edges here include surface access (v3 README), so only the access portion is hit: 0.85 [ASSUMPTION].
# Battery backup: ~half of Austin's signals have batteries lasting up to 6 h [SRC: Austin Monitor 2023].
#   No LA figure found (GAP); Austin's share is used as a placeholder.
# ---------------------------------------------------------------------------
SIGNAL_FACTOR = {"art": 0.40, "fwy": 0.85}
SIGNAL_BACKUP_SHARE = 0.5
SIGNAL_BACKUP_MIN = 6 * 60

# ---------------------------------------------------------------------------
# 5. Failure Mode Table rows added in the coupled model (rows 1, 2, 4, 5 stay in traffic v3)
# ---------------------------------------------------------------------------
MULTI_EDGE_ROWS = {   # rows 3 / 6: one edge closed + diversion on 2 adjacent edges
    "3": dict(H=0.008583638887, driver="human"),   # [DOC] column H, model-region per hour
    "6": dict(H=6.776557016e-05, driver="av"),     # [DOC]
}
MULTI_EDGE_DUR_H = (3.3, 0.8, 2.0, 5.6)  # [DOC] mean 3.3 h (Caltrans major incidents); sd and bounds [ASSUMPTION]
DIVERSION_FACTOR = (0.35, 0.78)          # [DOC] Lindley one-lane-blocked range reused for diversion edges [ASSUMPTION]

# Row 7: fleet-wide connectivity / remote-assist stall [DOC]
STALL_TOW_SHARE = 0.03            # [DOC] 2-3% of the active fleet needs a manual retrieval
STALL_SHORT_MIN = (2.0, 10.0)     # [DOC] >= 2 min by definition, most self-resolve; upper bound [ASSUMPTION]
STALL_TOW_MIN = (60.0, 120.0)     # [DOC] manual retrievals ~1-2 h
STALL_SUSPEND_H = (6.0, 20.0)     # [DOC] "~6 h to next day"; Dec 2025 SF pause ran Sat evening -> Sun afternoon
STALL_DARK_NODES = 3              # [ASSUMPTION] trigger: >= 3 of 10 nodes with dark signals (Dec 2025 SF:
                                  #   ~1/3 of PG&E SF customers out, >7,000 signals dark [DOC row 7 notes])
STALL_P_GIVEN_DARK = 0.5          # [ASSUMPTION] one documented event; same for every company (GAP)
STALL_ON_DARK_SIGNALS = True      # switch for the sensitivity run (Waymo shipped a fix in Jan 2026)

# Row 7b: battery depletion -> stalled in lane until towed [DOC]
TOW_7B_MIN = (30.0, 60.0)         # [DOC] AAA 30-60 min; 0.5-1 h lane occupancy

# Row 8: AV obstructs emergency response at an incident -> clearance extended [DOC]
AMP_EXTRA_MIN = (5, 15, 30)       # [DOC] +5 / +15 / +30 min
AMP_PER_AV_YEAR = 0.17            # [DOC] SFFD 2023: ~0.17 incidents per vehicle-year
# P(obstruction | incident starts on an edge with an AV on it). Calibrated by
# `python -m coupled.calibrate_row8` so the simulated rate is 0.17 per AV-year (seeds 0-19 weekday).
AMP_P_GIVEN_PRESENT = 0.000184   # 37.9 AV-present incidents/day, 15 AVs, 2.0 mi/kWh
AMP_P_BY_MPK = {2.0: 0.000184, 3.5: 0.000187}   # calibrated separately at each energy value (37.9 / 37.5 per day)

# ---------------------------------------------------------------------------
# 5b. AV energy use
# ---------------------------------------------------------------------------
# Traffic v3 used 3.5 mi/kWh [DOC notes "Waymo Number Breakdown"]. Waymo-modified I-Paces are estimated at
# 50-60 kWh/100 mi (~1.7-2.0 mi/kWh) [SRC: eletric-vehicles.com, citing prior estimates], and the I-Pace's
# 90 kWh battery [SRC: Jaguar/Waymo 2018 announcement] x 2.0 mi/kWh = 180 mi, the range already used here
# [DOC]. 3.5 mi/kWh would imply ~315 mi. The coupled model therefore uses 2.0; at the 1.8 kWh/min charger
# [DOC] that adds 3.6 mi of range per minute (3.5 mi/kWh: 6.3). The 3.5 results are kept for comparison.
AV_MI_PER_KWH = 2.0

# ---------------------------------------------------------------------------
# 6. Fleets
# ---------------------------------------------------------------------------
WAYMO = dict(name="Waymo", n_av=15, requests_per_day=170)   # v3 calibration: 5% AV VMT [DOC Assumptions!C9]
# Tesla enters with requests proportional to its fleet (same trips per vehicle as Waymo): the AV
# market grows rather than being split [ASSUMPTION]. No driverless Tesla service in LA exists to
# calibrate against, so fleet size is a sweep [USER].
TESLA_SIZES = (5, 10, 15)                                   # 1/3, 2/3, 1x Waymo's model fleet

# ---------------------------------------------------------------------------
# 7. Metrics
# ---------------------------------------------------------------------------
MAX_WAIT_MIN = 20.0   # v3: request cancelled after 20 min; the censored mean counts a cancellation as 20 min
