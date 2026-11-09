"""
Every modeling assumption for the grid layer, in one place.

Change values here, not inside the code. Anything marked ASSUMPTION is a
placeholder chosen by us, not taken from data, and should be stated as such
in any writeup.
"""

HOURS_PER_YEAR = 8760.0

# ---------------------------------------------------------------------------
# Feeder: IEEE 33-bus test feeder (Baran & Wu, 1989), loaded via pandapower.
# Bus numbers are 0-based (paper bus number = code bus number + 1).
# ---------------------------------------------------------------------------
SUBSTATION_VM_PU = 1.05     # ASSUMPTION: substation tap changer regulating high.
                            # At the case default of 1.00 the far end already sags
                            # to 0.913 p.u. with no depots.
V_MIN_PU = 0.95             # ANSI C84.1 Range A is +/-5 %
V_MAX_PU = 1.05
MAX_LOADING_PCT = 100.0     # line current must stay below its rating

TRUNK_LINES = [0, 1, 2, 3, 4]   # substation -> bus 5
TRUNK_RATING_KA = 0.30          # ASSUMPTION: the test case ships with no line ratings
OTHER_RATING_KA = 0.15          # ASSUMPTION

MAX_TIES_CLOSED = 2         # restoration may close up to this many tie switches at once
DEPOT_POWER_FACTOR = 0.95   # ASSUMPTION: lagging

# ---------------------------------------------------------------------------
# Depots: where each charging depot connects to the feeder.
#   bus       : feeder bus the depot is attached to
#   rated_mw  : the depot's full charging load (chosen so the intact feeder
#               passes limits; see hosting capacity results)
#   road_node : the matching node in the transportation graph -- FILL IN once
#               the depot <-> bus mapping is decided
# ---------------------------------------------------------------------------
DEPOTS = {
    "D_mid_trunk":      dict(bus=5,  rated_mw=0.30, road_node=None),
    "D_feeder_end":     dict(bus=17, rated_mw=0.05, road_node=None),
    "D_strong_lateral": dict(bus=21, rated_mw=0.50, road_node=None),
    "D_weak_lateral":   dict(bus=32, rated_mw=0.10, road_node=None),
}

# ---------------------------------------------------------------------------
# Routine (background) outages: random line failures on ordinary days.
# Source: SCE 2025 Annual Electric Reliability Report, via the project's
# Failure Mode Table (10-yr averages 2016-2025 for unplanned; 2023-2025 for planned).
# Each enabled class is converted to a per-line failure rate calibrated so the
# feeder reproduces the class's SAIFI; repair time is exponential with mean CAIDI.
# ---------------------------------------------------------------------------
ROUTINE_OUTAGE_CLASSES = {
    "unplanned": dict(saifi=0.9037, caidi_min=107.321, enabled=True),
    "planned":   dict(saifi=0.3113, caidi_min=300.183, enabled=False),
}
# Major event days, PSPS, wildfire, flood and earthquake are NOT routine:
# they are correlated, multi-element events, injected as hazard scenarios
# (see hazards.py).

# ---------------------------------------------------------------------------
# Hazard zones: which feeder lines sit in which hazard area.
# ASSUMPTION / PLACEHOLDER: the 33-bus feeder has no real geography. Replace
# these once feeder lines are tied to locations (same tagging as the road edges
# in the Failure Mode Table). Line indices: 17-20 = upper lateral (1-18-19-20-21),
# 21-23 = lateral 2-22-23-24, 28-31 = far end of lower lateral (28-...-32).
# ---------------------------------------------------------------------------
LINE_ZONES = {
    "WUI":              [17, 18, 19, 20, 28, 29, 30, 31],  # ~25 % of lines
    "floodplain_100yr": [22],
    "floodplain_500yr": [21, 22, 23],
}
# Buses located inside each zone. A zone-wide de-energization (e.g. PSPS) takes
# these out too, so restoration switching cannot feed power back into the zone.
ZONE_BUSES = {
    "WUI":              [18, 19, 20, 21, 29, 30, 31, 32],
    "floodplain_100yr": [23],
    "floodplain_500yr": [22, 23, 24],
}
