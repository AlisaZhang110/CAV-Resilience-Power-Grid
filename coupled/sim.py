"""
sim.py -- one simulated weekday with the grid layer and the traffic layer coupled.

    CoupledSim extends traffic/v3_time_of_day Sim (network, demand, BPR congestion, rows 1, 2, 4, 5)
    with:
      * GRID -> DEPOTS. Every minute the grid layer (IEEE 33-bus feeder, switching, AC power flow,
        curtailment) says how many MW each built depot can draw. 0 MW = depot dark (sessions
        interrupted, AVs re-route). 0 < MW < rated = PARTIAL CAPACITY: the available power is
        shared by the vehicles plugged in, so sessions run slower.
      * GRID -> SIGNALS. A road node whose feeder bus is dark (after switching) has dark traffic
        signals. Every edge touching it loses capacity (all-way-stop operation), with battery
        backup covering part of the first hours. Congestion follows automatically from BPR.
      * SEVERAL FLEETS. Each AV belongs to a company; each company sees only the depots in its
        access set (exclusive depots) or all of them (universal depots). Requests belong to a company.
      * NEW FAILURE MODES: rows 3/6 (major incident, >= 3 edges), 7 (fleet-wide stall, scheduled
        or triggered by dark signals), 7b (battery depletion blocks a lane until towed), 8 (AV
        obstructs incident clearance), and the scenario rows in scenarios.py.
    Rows 9 and 10 of v3 (independent per-depot outages) are replaced by the grid layer.
"""

import math
import random
from collections import defaultdict

from . import config as C
from av_traffic_sim_tod import NODES, Params, Sim, ekey, load_profiles  # noqa: F401


def _poisson(rng, lam):
    if lam > 50:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    L, k, prod = math.exp(-lam), 0, rng.random()
    while prod > L:
        k += 1
        prod *= rng.random()
    return k


class GridLink:
    """Grid layer queried by minute. Depots demand their rated MW (one-way coupling: the grid
    sets each depot's available capacity; see README for why two-way is not needed here)."""

    def __init__(self, feeder, built):
        self.feeder = feeder
        self.demand = {f"N{n}": (C.DEPOT_RATED_MW if n in built else 0.0) for n in C.NODE_BUS}
        self.outages = []
        self._cache = {}

    def set_events(self, events):
        self.outages = [o for ev in events for o in ev.to_outages()]

    def state(self, t_min):
        th = t_min / 60.0
        act = [o for o in self.outages if o.start_h <= th < o.end_h]
        lines = frozenset(o.index for o in act if o.element == "line")
        buses = frozenset(o.index for o in act if o.element == "bus")
        sub = not any(o.element == "substation" for o in act)
        key = (lines, buses, sub)
        if key not in self._cache:
            fs = self.feeder.solve(lines, buses, sub, self.demand)
            dark = frozenset(n for n, b in C.NODE_BUS.items() if b in fs.buses_dark)
            mw = {n: fs.depots[f"N{n}"]["deliverable_mw"] for n in C.NODE_BUS}
            self._cache[key] = (dark, mw)
        return self._cache[key]


class CoupledSim(Sim):
    def __init__(self, seed, fleets, access, built, events, feeder, signals=True, profiles=None, mi_per_kwh=None):
        """
        fleets : [dict(name, n_av, requests_per_day)]   (first fleet = Waymo, the v3 demand stream)
        access : {company: set of depot nodes it may charge at}
        built  : set of built depot nodes
        events : one day of scenario events (scenarios.py)
        """
        p = Params()
        p.hazards = ("1", "2", "4", "5")        # rows 9/10 now come from the grid layer
        p.n_av = sum(f["n_av"] for f in fleets)
        p.av_requests_per_day = fleets[0]["requests_per_day"]
        p.chargers = frozenset(built)
        p.ports_per_charger = C.PORTS_PER_DEPOT
        p.rain_day = events["rain"]
        p.forced_blocks = list(events["blocks"])
        p.mi_per_kwh = C.AV_MI_PER_KWH if mi_per_kwh is None else mi_per_kwh   # see config 5b
        super().__init__(p, seed, hazards_on=True, profiles=profiles)

        self.companies = [f["name"] for f in fleets]
        self.access = {co: frozenset(access[co]) & p.chargers for co in self.companies}
        i = 0
        for f in fleets:
            for _ in range(f["n_av"]):
                av = self.avs[i]
                av.co, av.stall_until, av.retire_at, av.q_since = f["name"], -1, None, None
                i += 1
        # demand: fleet 0 = the v3 stream (identical across configurations); others added with own rng
        av_dem = defaultdict(list)
        for t, lst in self.av_demand.items():
            av_dem[t] += [(o, d, fleets[0]["name"]) for o, d in lst]
        for k, f in enumerate(fleets[1:], start=1):
            rng = random.Random(seed * 7919 + 100 + k)
            for h in range(24):
                for _ in range(_poisson(rng, f["requests_per_day"] * self.av_share[h])):
                    o, d = self._pick_od(rng)
                    av_dem[h * 60 + rng.randrange(60)].append((o, d, f["name"]))
        self.av_demand = av_dem

        self.grid = GridLink(feeder, built)
        self.grid.set_events(events["grid"])
        self.signals_on = signals
        self.forced_caps = list(events["caps"])
        self.forced_stalls = list(events["stalls"])
        self.depot_mw = {n: C.DEPOT_RATED_MW for n in C.NODE_BUS}
        self.sig_dark = {}                          # node -> minute its signals went dark
        self.paused = {co: -1 for co in self.companies}
        self._cond_armed = False
        self._amp_extra_last = 0
        # separate random streams so configuration-dependent draws never shift the shared ones
        self.r3 = random.Random(seed * 7919 + 23)       # rows 3 / 6 (configuration-independent)
        self.r_amp = random.Random(seed * 7919 + 29)    # row 8
        self.r_7b = random.Random(seed * 7919 + 31)     # row 7b
        self.r_stall = random.Random(seed * 7919 + 37)  # row 7 effects
        self.r_cond = random.Random(seed * 7919 + 41)   # row 7 trigger on dark signals
        # extra bookkeeping
        self.amp_present = 0
        self.amp_events = 0
        self.queue_wait_min = 0.0
        self.sig_node_min = 0
        self.depot_dark_min = 0
        self.depot_partial_min = 0
        self.h_depot_frac = [0.0] * 24
        self.h_dark_nodes = [0.0] * 24
        self.stall_log = []

    # ------------------------------------------------------------------ hazards
    def update_hazards(self):
        t = self.t
        dark_nodes, mw = self.grid.state(t)
        self.depot_mw = mw
        for n in self.p.chargers:
            if mw[n] <= 1e-9:
                if n not in self.dark:
                    self._dark(n, math.inf, "grid")
            elif n in self.dark and self.dark[n][1] == "grid":
                del self.dark[n]
        if self.signals_on:
            for n in dark_nodes:
                self.sig_dark.setdefault(n, t)
            for n in list(self.sig_dark):
                if n not in dark_nodes:
                    del self.sig_dark[n]
        # row 7 triggered by a wide grid outage (Dec 2025 SF) -- one draw per outage episode
        if C.STALL_ON_DARK_SIGNALS and len(dark_nodes) >= C.STALL_DARK_NODES:
            if not self._cond_armed:
                self._cond_armed = True
                for co in self.companies:
                    if self.r_cond.random() < C.STALL_P_GIVEN_DARK:
                        self.start_stall(co, "7 (dark signals)")
        else:
            self._cond_armed = False
        for u, v, st, dur, f in self.forced_caps:
            if t == st:
                for de in ((u, v), (v, u)):
                    self.cap_events[de].append((t + dur, f, "scenario"))
        for co, st in self.forced_stalls:
            if t == st and co in self.companies:
                self.start_stall(co, "7")
        super().update_hazards()                       # expiry, forced blocks, rows 1, 2, 4, 5
        h = t // 60 % 24
        for row, hz in C.MULTI_EDGE_ROWS.items():      # rows 3 / 6
            tod = 24 * (self.h_vmt_share[h] if hz["driver"] == "human" else self.av_share[h])
            lam = hz["H"] * tod * (self.p.rain_incident_mult if self.p.rain_day else 1.0)
            if self.r3.random() < 1 - math.exp(-lam / 60):
                e = self.all_edges[self.r3.randrange(len(self.all_edges))]
                m, sd, lo, hi = C.MULTI_EDGE_DUR_H
                dur = min(max(self.r3.gauss(m, sd), lo), hi) * 60
                adj = [x for x in self.all_edges if x != e and set(x) & set(e)]
                div = self.r3.sample(adj, min(2, len(adj)))
                facs = [self.r3.uniform(*C.DIVERSION_FACTOR) for _ in div]
                extra = 0
                if e not in self.blocked:
                    self._block(e, dur, row)
                    extra = self._amp_extra_last           # row 8 extension, if any (fix a)
                for a, fac in zip(div, facs):
                    for de in (a, (a[1], a[0])):
                        self.cap_events[de].append((t + dur + extra, fac, row))

    def _log_event(self, row, where, start, dur, factor, sep=" -> "):
        extra = 0
        self._amp_extra_last = 0
        if row in ("1", "2", "3") and isinstance(where, tuple):     # row 8 amplifier
            e = ekey(*where)
            if any(a.state == "driving" and a.edge and ekey(*a.edge) == e for a in self.avs):
                self.amp_present += 1
                if self.r_amp.random() < C.AMP_P_BY_MPK.get(self.p.mi_per_kwh, C.AMP_P_GIVEN_PRESENT):
                    extra = self.r_amp.choice(C.AMP_EXTRA_MIN)
                    self.amp_events += 1
                    if row == "1" and self.cap_events[where]:
                        end, f, r = self.cap_events[where][-1]
                        self.cap_events[where][-1] = (end + extra, f, r)
                    elif e in self.blocked:
                        end, r = self.blocked[e]
                        self.blocked[e] = (end + extra, r)
        self._amp_extra_last = extra
        super()._log_event(row, where, start, dur + extra, factor, sep)
        if extra:
            self.event_log[-1]["row8_extra_min"] = extra

    def start_stall(self, co, row):
        t = self.t
        self.paused[co] = max(self.paused[co], t + self.r_stall.uniform(*C.STALL_SUSPEND_H) * 60)
        n_tow = 0
        for av in self.avs:
            if av.co != co or av.state != "driving":
                continue
            if self.r_stall.random() < C.STALL_TOW_SHARE:
                d = self.r_stall.uniform(*C.STALL_TOW_MIN)
                av.stall_until, av.retire_at = t + d, t + d
                f = self.r_stall.uniform(0.35, 0.78)            # stalled in a lane [DOC Lindley]
                self.cap_events[av.edge].append((t + d, f, "7"))
                n_tow += 1
            else:
                av.stall_until = t + self.r_stall.uniform(*C.STALL_SHORT_MIN)
        self.stall_log.append(dict(company=co, minute=t, row=row, towed=n_tow,
                                   suspended_until=round(self.paused[co])))
        self.hourly[t // 60 % 24]["events_row_7"] += 1

    # ------------------------------------------------------------------ signals
    def cap_factor(self, u, v):
        # Fix (c): independent cuts on the same road compound (product), instead of v3's worst-one-wins.
        if ekey(u, v) in self.blocked:
            return 0.0
        f = 1.0
        for _, fac, _ in self.cap_events[(u, v)]:
            f *= fac
        if self.p.rain_day:
            f *= self.p.rain_capacity_factor
        if f > 0 and self.sig_dark and (u in self.sig_dark or v in self.sig_dark):
            base = C.SIGNAL_FACTOR[self.g.edges[u, v]["cls"]]
            sf = 1.0
            for n in (u, v):
                if n in self.sig_dark:
                    x = base
                    if self.t - self.sig_dark[n] < C.SIGNAL_BACKUP_MIN:
                        x = 1 - (1 - base) * (1 - C.SIGNAL_BACKUP_SHARE)
                    sf = min(sf, x)
            f *= sf
        return f

    # ------------------------------------------------------------------ movement
    def _tti(self, u, v, q, cf):
        cap = self.p.capacity_vph[self.g.edges[u, v]["cls"]] * cf
        return min(1 + self.p.bpr_alpha * (q / cap) ** self.p.bpr_beta, self.p.max_tti)

    def take_next_edge(self, veh):
        super().take_next_edge(veh)
        if veh.state == "driving" and veh.edge is not None:
            de = veh.edge
            veh.edge_q = len(self.entries[de]) - 1     # flow the entry travel time was computed with
            veh.edge_cf = self.cap_factor(*de)
            veh.edge_total = veh.edge_left             # current estimate of the whole traversal time

    def _rescale_for_capacity(self, veh):
        """Fix (d): if the road's capacity factor changed since the car entered (incident, dark signals,
        cut lifted), stretch or shrink its remaining time by the ratio of BPR travel-time indices at the
        flow it entered with. Flow changes alone still do not touch cars already on the road (as in v3)."""
        cf = self.cap_factor(*veh.edge)
        old = getattr(veh, "edge_cf", cf)
        if cf > 0 and old > 0 and abs(cf - old) > 1e-9:
            u, v = veh.edge
            r = self._tti(u, v, veh.edge_q, cf) / self._tti(u, v, veh.edge_q, old)
            veh.edge_left *= r
            veh.edge_total *= r
            veh.edge_cf = cf

    def _strand_on_edge(self, veh, miles_done):
        """Fix (b), row 7b: the AV runs out of energy part-way along the road and blocks a lane there."""
        veh.range_mi = 0.0
        self.vmt["av_pax" if veh.leg == "in_service" else "av_empty"] += miles_done
        veh.state = "stranded"
        self.stranded.append(dict(av=veh.vid, minute=self.t, node=None,
                                  edge=f"{NODES[veh.edge[0]]} -> {NODES[veh.edge[1]]}", leg=veh.leg))
        if veh.req:
            self._log_request(veh.req, served=False, reason="vehicle stranded")
            veh.req = None
        fac, dur = self.r_7b.uniform(0.35, 0.78), self.r_7b.uniform(*C.TOW_7B_MIN)
        self.cap_events[veh.edge].append((self.t + dur, fac, "7b"))
        Sim._log_event(self, "7b", veh.edge, self.t, dur, fac)

    def advance(self, veh):
        if veh.is_av and veh.stall_until > self.t:
            veh.stuck_min += 1
            return
        if veh.edge is not None and ekey(*veh.edge) not in self.blocked:
            if hasattr(veh, "edge_total"):
                self._rescale_for_capacity(veh)
            if veh.is_av and hasattr(veh, "edge_total"):
                left = veh.edge_left - 1
                miles = self.g.edges[veh.edge]["miles"]
                done = miles if left <= 0.5 else miles * (1 - left / veh.edge_total)
                if veh.range_mi - done <= 0:
                    self._strand_on_edge(veh, max(veh.range_mi, 0.0))
                    return
        super().advance(veh)

    # ------------------------------------------------------------------ charging
    def depot_rate(self, n):
        base = self.p.charge_kwh_per_min * self.p.mi_per_kwh
        k = max(len(self.charging_at[n]), 1)
        return base * min(1.0, self.depot_mw.get(n, 0.0) / (k * C.PORT_MW))

    def nearest_charger(self, node, co=None):
        dist, _ = self.routes()
        best = None
        for c in self.working_chargers():
            if co is not None and c not in self.access[co]:
                continue
            if c not in dist[node]:
                continue
            busy = len(self.charging_at[c]) + len(self.charge_queue[c])
            sess = 20.0 * 3.5 / self.p.mi_per_kwh       # typical session: ~20 min at 3.5 mi/kWh, longer if less efficient
            wait = max(0, busy - C.PORTS_PER_DEPOT + 1) * sess / C.PORTS_PER_DEPOT
            frac = self.depot_mw[c] / C.DEPOT_RATED_MW
            slow = sess * (1.0 / max(frac, 0.05) - 1.0)                          # partial power
            score = dist[node][c] + wait + slow
            if best is None or score < best[0]:
                best = (score, c)
        return best[1] if best else None

    def send_to_charger(self, av):
        c = self.nearest_charger(av.node, av.co)
        if c is None:
            av.state = "idle"
            return
        self.start_leg(av, c, "to_charger")

    def try_charge(self, av):
        n = av.node
        if n in self.dark or n not in self.p.chargers or n not in self.access[av.co]:
            self.send_to_charger(av)
            return
        if len(self.charging_at[n]) >= C.PORTS_PER_DEPOT:
            av.state, av.q_since = "charge_queue", self.t
            self.charge_queue[n].append(av.vid)
            return
        if av.q_since is not None:
            self.queue_wait_min += self.t - av.q_since
            av.q_since = None
        av.state = "charging"
        self.charging_at[n].add(av.vid)
        self.charge_log.append(dict(av=av.vid, company=av.co, node=NODES[n], start_min=self.t,
                                    range_before=round(av.range_mi, 1),
                                    depot_power_frac=round(self.depot_mw[n] / C.DEPOT_RATED_MW, 3)))

    def step_charging(self, av):
        n = av.node
        av.range_mi = min(self.p.av_max_range_mi, av.range_mi + self.depot_rate(n))
        if av.range_mi >= self.p.av_max_range_mi - 1e-6:
            self.charging_at[n].discard(av.vid)
            av.state, av.leg = "idle", None
            if self.charge_queue[n]:
                nxt_id = self.charge_queue[n].popleft()
                nxt = next(a for a in self.avs if a.vid == nxt_id)
                self.try_charge(nxt)

    # ------------------------------------------------------------------ dispatch
    def dispatch(self):
        dist, paths = self.routes()
        still = []
        for r in self.pending:
            if self.t - r["request_min"] > self.p.av_max_wait_min:
                self._log_request(r, served=False, reason="no vehicle within max wait")
                continue
            co, o, d = r["co"], r["origin"], r["dest"]
            if self.paused[co] > self.t or d not in dist[o]:
                still.append(r)
                continue
            c = self.nearest_charger(d, co)
            after = (self.path_miles(paths[d][c]) + self.p.av_reserve_mi) if c is not None \
                else self.p.av_charge_threshold_mi
            trip_mi = self.path_miles(paths[o][d]) + after
            best = None
            for av in self.avs:
                if av.co != co or av.state != "idle" or o not in dist[av.node]:
                    continue
                if av.range_mi < self.path_miles(paths[av.node][o]) + trip_mi:
                    continue
                cand = (dist[av.node][o], av.vid, av)
                if best is None or cand[:2] < best[:2]:
                    best = cand
            if best is None:
                still.append(r)
                continue
            av = best[2]
            r["assign_min"], r["av"] = self.t, av.vid
            av.req = r
            self.start_leg(av, o, "to_pickup")
        self.pending = still

    def _log_request(self, r, served, reason=""):
        super()._log_request(r, served, reason)
        self.av_log[-1]["co"] = r["co"]

    # ------------------------------------------------------------------ main loop
    def step(self):
        t = self.t
        for de in list(self.entries):
            q = self.entries[de]
            while q and q[0] <= t - 60:
                q.popleft()
        self.update_hazards()
        for veh in self.humans + self.avs:
            if veh.is_av and veh.retire_at is not None and t >= veh.retire_at and veh.state != "towed":
                if veh.req:
                    self._log_request(veh.req, served=False, reason="vehicle retrieved (row 7)")
                    veh.req = None
                veh.state, veh.edge = "towed", None
                continue
            if veh.state == "driving":
                self.advance(veh)
            elif veh.state == "waiting":
                veh.wait_min += 1
                self.take_next_edge(veh)
            elif veh.state == "charging":
                self.step_charging(veh)
            elif veh.state == "idle" and veh.is_av and veh.range_mi < self.p.av_charge_threshold_mi:
                self.send_to_charger(veh)
        self.humans = [h for h in self.humans if h.state != "done"]
        hh = t // 60
        for o, d in self.human_demand.get(t, []):
            veh = self._new_human(o)
            self.hourly[hh]["human_dep"] += 1
            self.start_leg(veh, d, "trip")
        for o, d, co in self.av_demand.get(t, []):
            self.pending.append(dict(request_min=t, origin=o, dest=d, co=co))
            self.hourly[hh]["av_req"] += 1
        self.dispatch()
        # bookkeeping
        self.sig_node_min += len(self.sig_dark)
        fr = []
        for n in self.p.chargers:
            m = self.depot_mw[n]
            if m <= 1e-9:
                self.depot_dark_min += 1
            elif m < C.DEPOT_RATED_MW - 1e-6:
                self.depot_partial_min += 1
            fr.append(m / C.DEPOT_RATED_MW)
        self.h_depot_frac[hh] += (sum(fr) / len(fr)) / 60.0
        self.h_dark_nodes[hh] += len(self.grid.state(t)[0]) / 60.0
        self.t += 1

    def _new_human(self, o):
        from av_traffic_sim_tod import Veh
        veh = Veh(self.next_vid, False, o)
        self.next_vid += 1
        self.humans.append(veh)
        return veh

    # ------------------------------------------------------------------ outputs
    def metrics(self):
        s = self.summary()
        out = dict(
            human_trips=s["human_trips_completed"],
            human_delay_per_trip=s["human_total_delay_min"] / max(s["human_trips_completed"], 1),
            human_total_delay=s["human_total_delay_min"],
            mean_tti=sum(h["tti_sum"] for h in self.hourly) / max(sum(h["tti_n"] for h in self.hourly), 1),
            peak_tti=s["peak_hour_tti"],
            charge_sessions=len(self.charge_log),
            charge_queue_min=self.queue_wait_min,
            stranded=len(self.stranded),
            amp_present=self.amp_present, amp_events=self.amp_events,
            stall_events=len(self.stall_log),
            dark_signal_node_h=self.sig_node_min / 60.0,
            depot_dark_h=self.depot_dark_min / 60.0,
            depot_partial_h=self.depot_partial_min / 60.0,
        )
        for co in ["all"] + self.companies:
            rows = [r for r in self.av_log if co == "all" or r.get("co") == co]
            served = [r for r in rows if r["served"]]
            n = len(rows)
            wsum = sum(r["wait_min"] for r in served)
            out[f"{co}_requests"] = n
            out[f"{co}_served"] = len(served)
            out[f"{co}_unserved_pct"] = 100.0 * (n - len(served)) / n if n else 0.0
            out[f"{co}_wait_served"] = wsum / len(served) if served else 0.0
            out[f"{co}_rider_wait"] = (wsum + C.MAX_WAIT_MIN * (n - len(served))) / n if n else 0.0
        return out

    def hourly_series(self):
        return [dict(hour=h, depot_power_frac=round(self.h_depot_frac[h], 3),
                     dark_signal_nodes=round(self.h_dark_nodes[h], 2),
                     mean_tti=round(d["tti_sum"] / d["tti_n"], 3) if d["tti_n"] else None,
                     human_delay=round(d["human_delay"] / d["human_done"], 2) if d["human_done"] else None,
                     av_wait=round(d["av_wait"] / d["av_served"], 2) if d["av_served"] else None,
                     av_unserved=int(d["av_unserved"]), av_requests=int(d["av_req"]))
                for h, d in enumerate(self.hourly)]
