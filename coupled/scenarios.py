"""
scenarios.py -- the hazard layer: Failure Mode Table rows -> one simulated day.

Frequent rows (1, 1c, 2, 3, 4, 5, 6, 7b, 8) are sampled minute by minute inside every simulated
day (see sim.py). The rest are rare, so they are simulated *given that they happen*
(hazard-conditioned sampling) and weighted afterwards by their annual rate:

    annual value = 365 x ordinary-day mean  +  sum_s  rate_s x days_s x (scenario mean - ordinary mean)

Each scenario's `make(rng)` returns the events of one day:
    grid   : [HazardEvent]                (hours from midnight; grid layer)
    blocks : [(u, v, start_min, dur_min)] (edge closed both directions)
    caps   : [(u, v, start_min, dur_min, factor)] (capacity x factor, both directions)
    stalls : [(company, start_min)]       (row 7 fleet-wide stall)
    rain   : bool                         (row 1b)
Same seed -> same events for every depot configuration (common random numbers).
"""

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import config as C
from grid_layer import HazardEvent, psps, substation_loss, zone_event
from grid_layer import params as GP
from grid_layer.outages import calibrate_line_rate

from av_traffic_sim_tod import EDGES  # noqa: E402

FWY_EDGES = [(u, v) for u, v, c in EDGES if c == "fwy"]
ALL_EDGES = [(u, v) for u, v, _ in EDGES]
DAY = 24 * 60


@dataclass
class Scenario:
    key: str
    label: str
    rows: str
    rate_per_yr: float     # events per year touching the model area
    days: float            # days of impact per event (for annual weighting)
    basis: str             # where the rate comes from
    make: Callable


def _empty():
    return dict(grid=[], blocks=[], caps=[], stalls=[], rain=False)


def _lognormal(rng, mean, sigma):
    mu = math.log(mean) - sigma ** 2 / 2
    return float(rng.lognormal(mu, sigma))


def build_scenarios(feeder):
    """Scenario library. Needs the Feeder to turn per-customer SAIFI into feeder event rates."""
    lam_unpl, shares = calibrate_line_rate(feeder, GP.ROUTINE_OUTAGE_CLASSES["unplanned"]["saifi"])
    lam_plan, _ = calibrate_line_rate(feeder, GP.ROUTINE_OUTAGE_CLASSES["planned"]["saifi"])
    lines = sorted(feeder.normal_lines)
    n_lines = len(lines)

    # Row 10 (major event day): each line fails with p = 0.10 [ASSUMPTION]. The table's rate is
    # per customer (0.1834 interruptions / customer-yr), so the feeder event rate is
    # 0.1834 / E[share of customers interrupted per event]; that share is estimated here.
    rng0 = np.random.default_rng(12345)
    total = sum(feeder.customer_load.values())
    all_b = set(feeder.buses)
    fr = []
    for _ in range(2000):
        down = {ln for ln in lines if rng0.random() < 0.10}
        lost = all_b - feeder.energized(feeder.normal_lines - down)
        fr.append(sum(feeder.customer_load.get(b, 0.0) for b in lost) / total)
    med_share = float(np.mean(fr))

    def s_unplanned(rng):
        d = _empty()
        ln = int(rng.choice(lines))
        st = rng.uniform(0, 24)
        d["grid"].append(HazardEvent("row9_unplanned", st, rng.exponential(107.321 / 60), lines=[ln]))
        return d

    def s_planned(rng):
        d = _empty()
        ln = int(rng.choice(lines))
        st = rng.uniform(8, 10)   # [ASSUMPTION] scheduled in the morning work window
        d["grid"].append(HazardEvent("row11_planned", st, rng.exponential(300.183 / 60), lines=[ln]))
        return d

    def s_med(rng):
        d = _empty()
        st = rng.uniform(0, 24)
        down = [ln for ln in lines if rng.random() < 0.10] or [int(rng.choice(lines))]
        for ln in down:   # heavy tail [DOC row 10]: lognormal, mean 8.6 h, sigma 1 [ASSUMPTION]
            d["grid"].append(HazardEvent("row10_MED", st, _lognormal(rng, 516.914 / 60, 1.0), lines=[ln]))
        return d

    def s_psps(rng):
        d = _empty()
        d["grid"].append(psps(rng.uniform(4, 12), rng.uniform(24, 48)))   # [DOC] 24-48 h typical
        return d

    def s_rain(rng):
        d = _empty()
        d["rain"] = True
        return d

    def s_fire1(rng):
        d = _empty()
        u, v = C.WUI_EDGES[int(rng.integers(len(C.WUI_EDGES)))]
        d["blocks"].append((u, v, 0, DAY))   # [DOC] closed >= 24 h: closed the whole simulated day
        return d

    def s_fire3(rng):
        d = _empty()
        idx = rng.choice(len(C.WUI_EDGES), size=3, replace=False)
        for i in idx:
            u, v = C.WUI_EDGES[int(i)]
            d["blocks"].append((u, v, 0, DAY))
        # [DOC row 14] common-cause wind event: coincides with PSPS / MED -> WUI zone de-energized
        d["grid"].append(psps(0.0, 36.0))
        return d

    def s_flood100(rng):
        d = _empty()
        st, dur = rng.uniform(0, 18), rng.uniform(6, 24)    # [DOC] hours to 1-2 days
        u, v = C.FLOOD100_EDGES[0]
        d["blocks"].append((u, v, int(st * 60), dur * 60))
        d["grid"].append(zone_event("row15_flood", "floodplain_100yr", st, dur, whole_zone_dark=True))
        return d

    def s_flood500(rng):
        d = _empty()
        for u, v in C.FLOOD500_EDGES:
            d["blocks"].append((u, v, 0, DAY))              # [DOC] 1-3 days
        d["grid"].append(zone_event("row16_flood", "floodplain_500yr", 0.0, 48.0, whole_zone_dark=True))
        return d

    def s_quake(rng):
        d = _empty()
        st = rng.uniform(0, 24)
        t0 = int(st * 60)
        k = int(rng.integers(3, 5))                         # [DOC] ">= 3 edges"; Northridge damaged 4 freeways
        for i in rng.choice(len(FWY_EDGES), size=k, replace=False):
            u, v = FWY_EDGES[int(i)]
            d["blocks"].append((u, v, t0, DAY))             # [DOC] weeks to months
        for u, v in ALL_EDGES:                              # [DOC] inspection closures right after the event
            d["caps"].append((u, v, t0, 240.0, 0.7))        # x0.7 for 4 h [ASSUMPTION]
        d["grid"].append(substation_loss(st, rng.uniform(6, 24)))   # [ASSUMPTION] 6-24 h supply loss
        return d

    def s_stall(rng):
        d = _empty()
        d["stalls"].append(("Waymo", int(rng.uniform(0, 24) * 60)))
        return d

    H = lambda h: h * 8760.0   # column H (per hour, after area scaling) -> per year
    sc = [
        Scenario("rain", "Rain day", "1b", 34.1, 1, "[DOC] NOAA normals, 34.1 rain days/yr", s_rain),
        Scenario("line_fault", "Line fault (unplanned)", "9", lam_unpl * n_lines, 1,
                 f"[DOC] SCE SAIFI 0.904 -> {lam_unpl:.3f}/line-yr x {n_lines} lines", s_unplanned),
        Scenario("planned", "Planned outage", "11", lam_plan * n_lines, 1,
                 f"[DOC] SCE planned SAIFI 0.311 -> {lam_plan:.3f}/line-yr x {n_lines} lines", s_planned),
        Scenario("med", "Major event day (storm)", "10", 0.1834 / med_share, 1,
                 f"[DOC] 0.1834/customer-yr / {med_share:.2f} mean share interrupted", s_med),
        Scenario("psps", "PSPS (WUI zone)", "12", 5.0 * 0.10, 1.5,
                 "[DOC] 5 LA County events/yr x q = 0.10 [ASSUMPTION; q is a GAP]", s_psps),
        Scenario("fire1", "Wildfire, 1 edge closed", "13", H(1.26479921e-05), 10,
                 "[DOC] column H; median closure 1-2 weeks -> 10 days", s_fire1),
        Scenario("fire3", "Wildfire, 3 edges + PSPS", "14 (+12)", H(1.824229629e-06), 1.5,
                 "[DOC] column H; common-cause wind event", s_fire3),
        Scenario("flood100", "Flood, 100-yr edge", "15", 0.008 * len(C.FLOOD100_EDGES), 1,
                 "[DOC] 0.8%/yr per SFHA edge x 1 edge", s_flood100),
        Scenario("flood500", "Flood, 500-yr regional", "16", 0.002, 2,
                 "[DOC] 0.2%/yr regional AEP", s_flood500),
        Scenario("quake", "Earthquake M>=6.7", "18", 0.0305430244 * 0.75, 1,
                 "[DOC] UCERF3 0.0305/yr x P(>=3 edges | event) = 0.75 [ASSUMPTION, table range 0.5-1.0]",
                 s_quake),
        Scenario("stall", "AV fleet stall (Waymo)", "7", H(9.485994073e-06), 1,
                 "[DOC] column H (scenario row, ~1/yr city-wide x area factor)", s_stall),
    ]
    return {s.key: s for s in sc}


def ordinary(rng):
    return _empty()
