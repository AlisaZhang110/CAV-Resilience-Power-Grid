"""
feeder.py -- the physics of the grid layer.

Given which elements are out, `Feeder.solve()` answers:
  1. Which buses lost power?                      (graph search from the substation)
  2. Can tie switches bring them back?            (radial restoration, up to N ties)
  3. How much power can each depot still draw?    (AC power flow + curtailment)

No randomness and no time here. outages.py / hazards.py decide WHAT fails and
WHEN; this module decides what that means for each bus and depot.
"""

import importlib.util
import itertools
import warnings
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
import pandapower as pp
import pandapower.networks as pn

from . import params as P

warnings.filterwarnings("ignore")
_NUMBA = importlib.util.find_spec("numba") is not None
_TAN_PHI = float(np.tan(np.arccos(P.DEPOT_POWER_FACTOR)))


@dataclass
class FeederState:
    """Result of solving the feeder for one outage situation."""
    lines_down: frozenset
    buses_failed: frozenset
    substation_up: bool
    ties_closed: tuple                 # tie lines closed for restoration
    buses_dark_before: frozenset       # dark right after the failure, before switching
    buses_dark: frozenset              # still dark after switching
    bus_vm_pu: dict                    # voltage per energized bus
    max_loading_pct: float
    depot_supply_frac: float           # delivered / demanded MW, all depots (1 = fully served)
    depots: dict = field(default_factory=dict)
    # depots[name] = {"bus", "energized", "demand_mw", "deliverable_mw"}

    @property
    def v_min(self):
        return min(self.bus_vm_pu.values()) if self.bus_vm_pu else float("nan")


class Feeder:
    def __init__(self):
        net = pn.case33bw()
        net.ext_grid["vm_pu"] = P.SUBSTATION_VM_PU
        net.line["max_i_ka"] = P.OTHER_RATING_KA
        net.line.loc[P.TRUNK_LINES, "max_i_ka"] = P.TRUNK_RATING_KA

        self.customer_load = net.load.groupby("bus").p_mw.sum().to_dict()
        self.depot_load_idx = {}
        for name, d in P.DEPOTS.items():
            self.depot_load_idx[name] = pp.create_load(net, d["bus"], p_mw=0.0,
                                                       q_mvar=0.0, name=name)
        self.net = net
        self.buses = list(net.bus.index)
        self.ends = {int(i): (int(r.from_bus), int(r.to_bus)) for i, r in net.line.iterrows()}
        self.normal_lines = frozenset(int(i) for i in net.line.index[net.line.in_service])
        self.ties = tuple(int(i) for i in net.line.index[~net.line.in_service])
        self._cache = {}

    # ----------------------------------------------------------- topology
    def energized(self, closed_lines, buses_failed=frozenset()):
        """Buses reachable from the substation (bus 0) through closed lines."""
        adj = defaultdict(list)
        for ln in closed_lines:
            a, b = self.ends[ln]
            if a in buses_failed or b in buses_failed:
                continue
            adj[a].append(b)
            adj[b].append(a)
        seen, q = {0}, deque([0])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen

    def _is_radial(self, closed_lines, energized):
        """A tree with n nodes has n-1 edges; more means a loop."""
        n = sum(1 for ln in closed_lines
                if self.ends[ln][0] in energized and self.ends[ln][1] in energized)
        return n == len(energized) - 1

    # ----------------------------------------------------------- power flow
    def power_flow(self, closed_lines, buses_failed=frozenset(), depot_mw=None,
                   extra_load=None):
        """
        AC power flow for one configuration. Returns dict(ok, vm, max_loading,
        binding) or None if it does not converge. extra_load=(bus, mw) adds a
        test load (used by the hosting-capacity study).
        """
        net = self.net
        net.line["in_service"] = net.line.index.isin(list(closed_lines))
        net.bus["in_service"] = ~net.bus.index.isin(list(buses_failed))
        depot_mw = depot_mw or {}
        for name, li in self.depot_load_idx.items():
            p = depot_mw.get(name, 0.0)
            net.load.at[li, "p_mw"] = p
            net.load.at[li, "q_mvar"] = p * _TAN_PHI
        tmp = None
        if extra_load:
            tmp = pp.create_load(net, extra_load[0], p_mw=extra_load[1],
                                 q_mvar=extra_load[1] * _TAN_PHI)
        try:
            pp.runpp(net, numba=_NUMBA)
        except pp.LoadflowNotConverged:
            return None
        finally:
            if tmp is not None:
                net.load.drop(tmp, inplace=True)
        vm = net.res_bus.vm_pu.dropna()
        ld = net.res_line.loading_percent.dropna()
        v_lo, v_hi = vm.min(), vm.max()
        max_ld = ld.max() if len(ld) else 0.0
        binding = []
        if v_lo < P.V_MIN_PU:
            binding.append(f"undervoltage @ bus {vm.idxmin()}")
        if v_hi > P.V_MAX_PU:
            binding.append(f"overvoltage @ bus {vm.idxmax()}")
        if max_ld > P.MAX_LOADING_PCT:
            binding.append(f"overload @ line {ld.idxmax()}")
        return {"ok": not binding, "vm": vm.to_dict(), "max_loading": float(max_ld),
                "binding": "; ".join(binding)}

    # ----------------------------------------------------------- main entry
    def solve(self, lines_down=(), buses_failed=(), substation_up=True, depot_demand=None):
        """
        Full grid response to an outage situation.

        lines_down    : line indices out of service (failed)
        buses_failed  : buses whose equipment failed (bus and its load are lost)
        substation_up : False = loss of supply at bus 0 (everything dark)
        depot_demand  : {depot: MW} wanted this hour; default = rated_mw

        Steps
          1. Topology: buses cut off from bus 0.
          2. Restoration: try closing 0..MAX_TIES_CLOSED tie switches. Accept only
             radial configurations that carry all restored CUSTOMER load within
             limits (depots off). Choose the one restoring the most customer load,
             then fewest switch operations, then highest minimum voltage.
          3. Curtailment: in that configuration, reduce depot load until every limit
             is satisfied. Depots restored by switching are cut first; depots that
             never lost power are cut only if that is not enough.
        Results are cached, so repeated situations cost nothing.
        """
        lines_down = frozenset(lines_down)
        buses_failed = frozenset(buses_failed)
        if depot_demand is None:
            depot_demand = {n: d["rated_mw"] for n, d in P.DEPOTS.items()}
        key = (lines_down, buses_failed, substation_up,
               tuple(sorted((n, round(v, 4)) for n, v in depot_demand.items())))
        if key in self._cache:
            return self._cache[key]

        all_b = frozenset(self.buses)
        base_closed = self.normal_lines - lines_down

        if not substation_up:
            state = self._dark_state(lines_down, buses_failed, all_b, depot_demand)
            self._cache[key] = state
            return state

        dark0 = all_b - self.energized(base_closed, buses_failed)

        # --- 2. restoration
        usable = [t for t in self.ties if t not in lines_down
                  and not (set(self.ends[t]) & buses_failed)]
        best = None
        combos = [()] if not dark0 else itertools.chain.from_iterable(
            itertools.combinations(usable, k) for k in range(P.MAX_TIES_CLOSED + 1))
        for combo in combos:
            closed = base_closed | set(combo)
            on = self.energized(closed, buses_failed)
            dark = all_b - on
            if combo and dark >= dark0:
                continue                                  # restores nothing
            if not self._is_radial(closed, on):
                continue                                  # would create a loop
            pf = self.power_flow(closed, buses_failed, depot_mw={})
            if pf is None or (combo and not pf["ok"]):
                continue                                  # customers alone violate limits
            served = sum(self.customer_load.get(b, 0.0) for b in on)
            score = (served, -len(combo), min(pf["vm"].values()))
            if best is None or score > best[0]:
                best = (score, combo, closed, dark)
        _, combo, closed, dark = best

        # --- 3. curtailment
        # Depots brought back by switching ride on borrowed capacity, so they are
        # curtailed first (group A). Depots that never lost power (group B) are
        # only curtailed if cutting group A to zero is not enough.
        on_depots = {n for n, d in P.DEPOTS.items() if d["bus"] not in dark}
        group_a = {n for n in on_depots if P.DEPOTS[n]["bus"] in dark0}
        group_b = on_depots - group_a
        if not group_a:                     # nothing transferred: curtail everyone together
            group_a, group_b = group_b, set()
        dem = {n: depot_demand.get(n, 0.0) for n in on_depots}

        def pf_at(sa, sb):
            mw = {n: (sa if n in group_a else sb) * v for n, v in dem.items()}
            return self.power_flow(closed, buses_failed, mw)

        def largest_ok(fn):
            """Largest s in [0, 1] with fn(s) within limits (bisection, ~0.001)."""
            r = fn(1.0)
            if r is not None and r["ok"]:
                return 1.0, r
            lo, hi, r_lo = 0.0, 1.0, fn(0.0)
            if r_lo is None or not r_lo["ok"]:
                return None, r_lo
            for _ in range(10):
                mid = (lo + hi) / 2
                r = fn(mid)
                if r is not None and r["ok"]:
                    lo, r_lo = mid, r
                else:
                    hi = mid
            return lo, r_lo

        s_a, pf = largest_ok(lambda s: pf_at(s, 1.0))
        s_b = 1.0
        if s_a is None:                     # even group A at zero is not enough
            s_a = 0.0
            s_b, pf = largest_ok(lambda s: pf_at(0.0, s))
            if s_b is None:                 # should not happen: customers-only case passed
                s_b, pf = 0.0, pf_at(0.0, 0.0)

        depots = {}
        for n, d in P.DEPOTS.items():
            on = n in on_depots
            s = s_a if n in group_a else s_b
            depots[n] = {"bus": d["bus"], "energized": on,
                         "demand_mw": depot_demand.get(n, 0.0),
                         "deliverable_mw": round(s * depot_demand.get(n, 0.0), 4) if on else 0.0}
        total_demand = sum(v["demand_mw"] for v in depots.values())
        overall = (sum(v["deliverable_mw"] for v in depots.values()) / total_demand
                   if total_demand > 0 else 1.0)
        state = FeederState(lines_down, buses_failed, True, tuple(combo), frozenset(dark0),
                            frozenset(dark), pf["vm"], pf["max_loading"], round(overall, 4), depots)
        self._cache[key] = state
        return state

    def _dark_state(self, lines_down, buses_failed, all_b, depot_demand):
        depots = {n: {"bus": d["bus"], "energized": False,
                      "demand_mw": depot_demand.get(n, 0.0), "deliverable_mw": 0.0}
                  for n, d in P.DEPOTS.items()}
        return FeederState(lines_down, buses_failed, False, (), all_b, all_b, {}, 0.0, 0.0, depots)

    def line_between(self, a, b):
        """Line index connecting buses a and b."""
        for ln, (x, y) in self.ends.items():
            if {x, y} == {a, b}:
                return ln
        raise ValueError(f"No line between bus {a} and bus {b}")
