"""
studies.py -- one-off planning studies on the feeder (not part of the hourly loop).

  hosting_capacity() : largest depot each bus can host with nothing failed
  n_minus_1()        : every single-line outage -> what goes dark, what switching
                       restores, what each depot can still draw
  validate_routine() : check the routine outage model reproduces SAIFI / SAIDI
"""

import numpy as np
import pandas as pd

from . import params as P
from .feeder import Feeder
from .outages import RoutineOutages


def hosting_capacity(feeder=None, buses=None, step_mw=0.1, max_mw=10.0):
    """For each bus alone (no depots), raise a test load until a limit is violated."""
    f = feeder or Feeder()
    rows = []
    for b in buses or [x for x in f.buses if x != 0]:
        p, last, binding = 0.0, 0.0, ""
        while p < max_mw:
            p = round(p + step_mw, 4)
            r = f.power_flow(f.normal_lines, extra_load=(b, p))
            if r is None or not r["ok"]:
                binding = "no convergence" if r is None else r["binding"]
                break
            last = p
        rows.append({"bus": b, "hosting_capacity_mw": last, "binding_constraint": binding})
    return pd.DataFrame(rows)


def n_minus_1(feeder=None):
    """Single-line outages with depots at rated load."""
    f = feeder or Feeder()
    rows = []
    for ln in sorted(f.normal_lines):
        s = f.solve(lines_down={ln})
        a, b = f.ends[ln]
        row = {"line": ln, "from-to": f"{a}-{b}",
               "buses_dark_before": len(s.buses_dark_before),
               "ties_closed": "-".join(str(t) for t in s.ties_closed) or "-",
               "buses_dark_after": len(s.buses_dark),
               "depot_supply_frac": s.depot_supply_frac,
               "v_min": round(s.v_min, 3)}
        for n, d in s.depots.items():
            row[n + "_mw"] = d["deliverable_mw"]
        rows.append(row)
    return pd.DataFrame(rows)


def validate_routine(years=5000, seed=0, feeder=None):
    """
    Simulate many years of routine outages (topology only, no power flow, no
    switching) and compare load-weighted SAIFI / SAIDI with the inputs.
    """
    f = feeder or Feeder()
    ro = RoutineOutages(f)
    rng = np.random.default_rng(seed)
    T = years * P.HOURS_PER_YEAR
    events = ro.sample(T, rng)
    total = sum(f.customer_load.values())
    all_b = set(f.buses)
    # sweep over change points
    pts = sorted([(o.start_h, 1, o.index) for o in events] + [(o.end_h, -1, o.index) for o in events])
    down, prev_dark, t_prev = {}, set(), 0.0
    cust_int, cust_hours = 0.0, 0.0
    cache = {}
    for t, kind, ln in pts:
        w = sum(f.customer_load.get(b, 0) for b in prev_dark) / total
        cust_hours += w * (t - t_prev)
        down[ln] = down.get(ln, 0) + kind
        failed = frozenset(k for k, v in down.items() if v > 0)
        if failed not in cache:
            cache[failed] = all_b - f.energized(f.normal_lines - failed)
        dark = cache[failed]
        cust_int += sum(f.customer_load.get(b, 0) for b in dark - prev_dark) / total
        prev_dark, t_prev = dark, t
    saifi_in = sum(c["saifi"] for c in ro.classes.values())
    saidi_in = sum(c["saifi"] * c["caidi_min"] for c in ro.classes.values())
    return {"years": years, "SAIFI_input": saifi_in, "SAIFI_simulated": round(cust_int / years, 3),
            "SAIDI_input_min": round(saidi_in, 1),
            "SAIDI_simulated_min": round(cust_hours / years * 60, 1)}
