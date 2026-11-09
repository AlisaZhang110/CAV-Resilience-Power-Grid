"""
layer.py -- the grid layer as one object with an hourly clock.

This is the piece the rest of the simulation talks to:

    grid = GridLayer(seed=1)
    grid.reset(n_days=3, hazards=[psps(start_h=10, duration_h=30)])
    for t in range(grid.horizon_h):
        state = grid.step(t)                    # or grid.step(t, depot_demand={...})
        capacity = state.depot_mw               # -> transportation layer
        ...

or, when the grid does not depend on the fleet (one-way coupling), all at once:

    run = grid.simulate(n_days=7, hazards=[...])
    run.bus_table()      # state of every bus, every hour
    run.depot_table()    # charging capacity of every depot, every hour
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import params as P
from .feeder import Feeder
from .outages import RoutineOutages


@dataclass
class HourState:
    """Everything the grid layer knows at one hour."""
    t: int                      # hours since simulation start
    lines_down: tuple
    buses_failed: tuple
    substation_up: bool
    causes: tuple               # what caused the active outages
    ties_closed: tuple
    buses_dark_before: tuple    # dark before switching
    buses_dark: tuple           # dark after switching
    bus_vm_pu: dict
    v_min: float
    max_loading_pct: float
    depot_supply_frac: float
    depots: dict                # name -> {bus, energized, demand_mw, deliverable_mw}

    @property
    def day(self):
        return self.t // 24

    @property
    def hour(self):
        return self.t % 24

    @property
    def depot_mw(self):
        """{depot: deliverable MW} -- the number the transportation layer needs."""
        return {n: d["deliverable_mw"] for n, d in self.depots.items()}


class GridLayer:
    def __init__(self, seed=None, routine=True, feeder=None):
        self.feeder = feeder or Feeder()
        self.routine = RoutineOutages(self.feeder) if routine else None
        self.rng = np.random.default_rng(seed)
        self.outages = []
        self.horizon_h = 0

    def reset(self, n_days=1, hazards=()):
        """Draw routine outages for the horizon and add hazard events."""
        self.horizon_h = int(24 * n_days)
        self.outages = self.routine.sample(self.horizon_h, self.rng) if self.routine else []
        for hz in hazards:
            self.outages += hz.to_outages()
        return self

    def step(self, t, depot_demand=None):
        """
        Grid state for hour t. depot_demand={depot: MW} lets the transportation
        layer say how much each depot wants this hour (two-way coupling);
        omit it to assume every depot draws its rated load.
        """
        active = [o for o in self.outages if o.active_in_hour(t)]
        lines = {o.index for o in active if o.element == "line"}
        buses = {o.index for o in active if o.element == "bus"}
        sub_up = not any(o.element == "substation" for o in active)
        fs = self.feeder.solve(lines, buses, sub_up, depot_demand)
        return HourState(t, tuple(sorted(lines)), tuple(sorted(buses)), sub_up,
                         tuple(sorted({o.cause for o in active})), fs.ties_closed,
                         tuple(sorted(fs.buses_dark_before)), tuple(sorted(fs.buses_dark)),
                         fs.bus_vm_pu, fs.v_min, fs.max_loading_pct, fs.depot_supply_frac,
                         fs.depots)

    def simulate(self, n_days=1, hazards=(), depot_demand_fn=None):
        """Reset and step through every hour. depot_demand_fn(t) -> {depot: MW} is optional."""
        self.reset(n_days, hazards)
        states = [self.step(t, depot_demand_fn(t) if depot_demand_fn else None)
                  for t in range(self.horizon_h)]
        return GridRun(states, self.outages)


class GridRun:
    """Hour-by-hour results of one simulation, with table views."""

    def __init__(self, states, outages):
        self.states = states
        self.outages = outages

    def summary(self, only_events=False):
        rows = []
        for s in self.states:
            dark_depots = [n for n, d in s.depots.items() if not d["energized"]]
            row = {"day": s.day, "hour": s.hour, "causes": ", ".join(s.causes) or "-",
                   "lines_down": list(s.lines_down), "substation_up": s.substation_up,
                   "ties_closed": list(s.ties_closed),
                   "buses_dark_before": len(s.buses_dark_before),
                   "buses_dark": len(s.buses_dark),
                   "depots_dark": ", ".join(dark_depots) or "-",
                   "depot_supply_frac": s.depot_supply_frac,
                   "v_min": round(s.v_min, 3) if s.bus_vm_pu else np.nan,
                   "max_loading_pct": round(s.max_loading_pct, 1)}
            rows.append(row)
        df = pd.DataFrame(rows)
        if only_events:
            df = df[(df.causes != "-")]
        return df

    def periods(self, only_events=True):
        """Collapse consecutive hours with the same grid state into one row (start-end)."""
        df = self.summary()
        keys = ["causes", "lines_down", "substation_up", "ties_closed", "buses_dark_before",
                "buses_dark", "depots_dark", "depot_supply_frac"]
        sig = df[keys].astype(str).agg("|".join, axis=1)
        grp = (sig != sig.shift()).cumsum()
        rows = []
        for _, g in df.groupby(grp):
            r = g.iloc[0].to_dict()
            r["from"] = f"d{int(g.day.iloc[0])} {int(g.hour.iloc[0]):02d}:00"
            end_t = int(g.day.iloc[-1]) * 24 + int(g.hour.iloc[-1]) + 1
            r["to"] = f"d{end_t // 24} {end_t % 24:02d}:00"
            r["hours"] = len(g)
            rows.append(r)
        out = pd.DataFrame(rows)
        if only_events and not out.empty:
            out = out[out.causes != "-"]
        cols = ["from", "to", "hours", "causes", "lines_down", "substation_up", "ties_closed",
                "buses_dark_before", "buses_dark", "depots_dark", "depot_supply_frac", "v_min"]
        return out[cols] if not out.empty else out

    def bus_table(self):
        """One row per bus per hour: energized?, voltage, depot attached."""
        depot_at = {d["bus"]: n for n, d in P.DEPOTS.items()}
        rows = []
        for s in self.states:
            dark = set(s.buses_dark)
            for b in range(33):
                rows.append({"day": s.day, "hour": s.hour, "bus": b,
                             "energized": b not in dark,
                             "restored_by_switching": b in s.buses_dark_before and b not in dark,
                             "vm_pu": round(s.bus_vm_pu.get(b, np.nan), 4),
                             "depot": depot_at.get(b, "")})
        return pd.DataFrame(rows)

    def depot_table(self):
        """One row per depot per hour: energized?, demand and deliverable MW."""
        rows = []
        for s in self.states:
            for n, d in s.depots.items():
                rows.append({"day": s.day, "hour": s.hour, "depot": n, "bus": d["bus"],
                             "road_node": P.DEPOTS[n]["road_node"],
                             "energized": d["energized"], "demand_mw": d["demand_mw"],
                             "deliverable_mw": d["deliverable_mw"]})
        return pd.DataFrame(rows)

    def outage_log(self):
        return pd.DataFrame([o.__dict__ for o in self.outages]).sort_values("start_h") \
            if self.outages else pd.DataFrame(columns=["element", "index", "start_h", "end_h", "cause"])
