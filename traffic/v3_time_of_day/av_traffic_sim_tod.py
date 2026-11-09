"""
Project #4 - 10-node AV/HV traffic simulation with time-of-day demand (v3)
==========================================================================

What changed from ../v2_failure_mode_2/av_traffic_sim.py
  * Demand follows an hourly profile instead of 100 cars looping all day.
      - Human trips: one vehicle per trip, spawned at its departure time and removed on arrival.
        Hourly shape = 2017 NHTS, LA-Long Beach-Anaheim CBSA, household-vehicle driver trips.
      - AV trips: ride requests served by a fixed AV fleet (dispatch, empty "deadhead" miles to the
        pickup, range-aware acceptance, charging). Hourly shape = 2017 NHTS taxi/TNC trips (US).
      - Weekday and weekend profiles. Demand for a seed is pre-generated, so the baseline run and the
        hazard run see exactly the same trips (common random numbers).
  * Congestion (Failure Mode Table row 1c, recurring congestion): edge travel time follows the BPR
    volume-delay function, so the AM/PM peaks slow traffic and incidents hurt more at peak.
  * Edges are tagged freeway / arterial, which (a) sets capacity and free-flow speed and (b) lets
    freeway-only rows (2, 5) use the edge count their per-edge rate was computed for.
  * More failure modes: rows 1, 2, 4, 5 (edge incidents, human and AV, reduced and no capacity),
    1b (rain day), 1c (recurring congestion), 9 and 10 (depot/charger power outages), plus
    forced scenarios for any edge block or charger outage (e.g., row 11 planned outage).
  * Incident rates follow exposure: hourly rate = daily-average rate x (24 x that hour's VMT share).

Tags: [DOC] from the Failure Mode Table / Project notes, [DATA] computed from a public dataset
(see demand_profiles.csv and README), [USER] from the task spec, [ASSUMPTION] chosen here.

Run:
    python av_traffic_sim_tod.py                         # baseline (congestion only) vs all hazards, seed 1
    python av_traffic_sim_tod.py --day-type weekend
    python av_traffic_sim_tod.py --force 5-6@480+60      # block Culver City-Downtown 08:00-09:00
    python av_traffic_sim_tod.py --outage 6@1020+120     # Downtown charger dark 17:00-19:00
    python av_traffic_sim_tod.py --rain                  # rain day (row 1b)
    python av_traffic_sim_tod.py --sweep --sweep-start 480   # each edge blocked 60 min at 08:00
    python av_traffic_sim_tod.py --days 100              # averages over 100 days
    python av_traffic_sim_tod.py --calibrate             # peak hourly flows, for setting capacities
Requires: networkx.
"""

import argparse
import csv
import math
import os
import random
from collections import defaultdict, deque
from dataclasses import dataclass, field

import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1. NETWORK  [DOC: Project_4 notes, page 5 hand-drawn graph]
# ---------------------------------------------------------------------------
NODES = {
    1: "Santa Monica", 2: "Sawtelle", 3: "West Hollywood", 4: "LAX", 5: "Culver City",
    6: "Downtown LA", 7: "Playa del Rey", 8: "Mid-City", 9: "Hollywood", 10: "Pasadena",
}
CHARGERS = set(NODES)  # [USER] every node is a charger (notes p.5 originally {1, 2, 4, 5})

# (u, v, class). Class is an [ASSUMPTION] based on the main road that links the two neighbourhoods:
#   fwy: 1-2 I-10, 2-5 I-405, 5-4 I-405, 5-7 SR-90, 5-6 I-10, 8-6 I-10, 9-6 US-101,
#        6-10 SR-110 / I-5, 9-10 US-101 + SR-134
#   art: 2-3 Santa Monica Blvd, 3-9 Sunset / Santa Monica Blvd, 1-5 Venice / Washington Blvd,
#        1-7 Lincoln Blvd, 3-5 La Cienega Blvd, 5-8 Venice / Washington Blvd, 4-8 La Cienega / La Brea,
#        8-9 La Brea / Highland
# 9 freeway edges matches the Failure Mode Table's Assumptions!C38 (9 freeway-dominated edges).
EDGES = [
    (1, 2, "fwy"), (2, 3, "art"), (3, 9, "art"), (9, 10, "fwy"), (1, 5, "art"), (1, 7, "art"),
    (2, 5, "fwy"), (3, 5, "art"), (5, 6, "fwy"), (5, 4, "fwy"), (5, 8, "art"), (5, 7, "fwy"),
    (4, 8, "art"), (8, 9, "art"), (8, 6, "fwy"), (9, 6, "fwy"), (6, 10, "fwy"),
]
COORDS = {  # (lat, lon), approximate neighbourhood centroids [ASSUMPTION]
    1: (34.0195, -118.4912), 2: (34.0390, -118.4430), 3: (34.0900, -118.3617),
    4: (33.9416, -118.4085), 5: (34.0211, -118.3965), 6: (34.0522, -118.2437),
    7: (33.9570, -118.4440), 8: (34.0420, -118.3550), 9: (34.0928, -118.3287),
    10: (34.1478, -118.1445),
}
CIRCUITY = 1.3  # [ASSUMPTION] road / straight-line distance


def haversine_mi(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 3958.8 * math.asin(math.sqrt(h))


def ekey(u, v):
    return (u, v) if u < v else (v, u)


# ---------------------------------------------------------------------------
# 2. DEMAND PROFILES  [DATA: demand_profiles.csv, built from 2017 NHTS; see build_profiles.py]
# ---------------------------------------------------------------------------
def load_profiles(path=os.path.join(HERE, "demand_profiles.csv")):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    prof = {}
    for col in rows[0]:
        if col == "hour" or "_n_" in col:
            continue
        vals = [float(r[col]) for r in rows]
        s = sum(vals)
        prof[col] = [v / s for v in vals]  # shares summing to 1
    return prof


# ---------------------------------------------------------------------------
# 3. PARAMETERS
# ---------------------------------------------------------------------------
@dataclass
class Params:
    sim_minutes: int = 24 * 60          # [DOC] 1 day
    day_type: str = "weekday"           # weekday | weekend
    # --- demand ---
    human_trips_per_day: int = 4000     # [ASSUMPTION] model scale: weekday trips (agents, not real vehicles)
    weekend_trip_factor: float = 0.81   # [DATA] NHTS 2017 LA CBSA: weekend-day / weekday-day driver trips
                                        #   (weighted totals / 104 and / 261 days)
    av_requests_per_day: int = 170      # [ASSUMPTION] tuned so AV VMT is ~5% of total
                                        #   ([DOC] Assumptions!C9 = 5% AV share of VMT); same on weekends
    n_av: int = 15                      # [ASSUMPTION] smallest of {10,12,15,20} with no unserved
                                        #   requests on a no-hazard weekday (mean wait ~6 min)
    node_weights: dict = None           # [ASSUMPTION] None = uniform origins/destinations
    av_max_wait_min: float = 20.0       # [ASSUMPTION] request cancelled if not picked up in 20 min
    # --- network speeds / capacity ---
    ff_speed_mph: dict = field(default_factory=lambda: {"fwy": 45.0, "art": 25.0})
    # [ASSUMPTION] free-flow speeds. Arterial 25 mph = v2 value. Freeway 45 mph is an
    # inter-neighbourhood average incl. ramps/surface access, not a posted limit.
    capacity_vph: dict = field(default_factory=lambda: {"fwy": 30.0, "art": 12.0})
    # Capacity per direction, in MODEL vehicles/hour (one agent stands for many real vehicles).
    #   Ratio fwy:art = 2.5 [ASSUMPTION: ~4 freeway lanes vs ~2 arterial lanes with signal losses].
    #   Level: calibrated so weekday baseline freeway delay ~ 0.16 min per freeway mile, the Caltrans
    #   D7 Q1 2022 average (23 M veh-h delay / 8.5 B freeway VMT) [DOC: table row 1c]. That figure
    #   averages all days and its speed threshold was not checked, so treat it as order-of-magnitude.
    bpr_alpha: float = 0.15             # [DOC-std] BPR (Bureau of Public Roads 1964) coefficients
    bpr_beta: float = 4.0
    max_tti: float = 6.0                # [ASSUMPTION] cap travel-time index on a reduced-capacity edge
    congestion: bool = True
    # --- AV energy ---  [DOC: notes "Waymo Number Breakdown"]
    av_max_range_mi: float = 180.0
    charge_kwh_per_min: float = 1.8
    mi_per_kwh: float = 3.5
    av_start_range_mi: tuple = (60.0, 180.0)   # [ASSUMPTION]
    av_charge_threshold_mi: float = 50.0       # [USER]
    av_reserve_mi: float = 10.0                # [ASSUMPTION] must still reach a charger with 10 mi left
    ports_per_charger: int = None              # [ASSUMPTION] None = unlimited ports
    chargers: frozenset = frozenset(CHARGERS)  # depot nodes; --chargers 1,2,4,5 for the notes' set
    # --- hazards ---
    hazards: tuple = ("1", "2", "4", "5", "9", "10")
    rain_day: bool = False                     # row 1b
    rain_incident_mult: float = 2.33           # [DOC] row 1b: 3.5 vs 1.5 accidents/shift (I-880)
    rain_capacity_factor: float = 0.92         # [ASSUMPTION] row 1b CAF is a GAP in the table (HCM)
    forced_blocks: list = field(default_factory=list)    # [(u, v, start, dur)]
    forced_outages: list = field(default_factory=list)   # [(node, start, dur)]


# Failure Mode Table rows used here. H = P per hour AFTER area scaling, model-region total
# (column H). The per-edge rate is H / (number of applicable edges IN THIS GRAPH), so the
# region-wide rate in the table is preserved (column R divides by the table's assumed 15 edges).
EDGE_HAZARDS = {
    #  row: (H, applies_to, kind, driver)
    "1": dict(H=6.623330441, edges="all", kind="reduce", driver="human"),
    "2": dict(H=0.02077195552, edges="fwy", kind="block", driver="human"),
    "4": dict(H=0.1564214342, edges="all", kind="reduce", driver="av"),
    "5": dict(H=0.000411102208, edges="fwy", kind="block", driver="av"),
}
# Node (depot) power outages: per-node rate per year and mean duration. [DOC] rows 9 and 10.
NODE_HAZARDS = {
    "9": dict(per_year=0.9037, mean_min=107.321),
    "10": dict(per_year=0.1834, mean_min=516.914),
}


def sample_reduce_event(rng):
    """Rows 1 / 4: duration and remaining-capacity factor."""
    dur = rng.uniform(15.0, 24.0)  # [DOC] 0.25-0.4 h (LA FSP 15.1 min on scene + wait); uniform = [ASSUMPTION]
    if rng.random() < 0.103:       # [DOC] Assumptions!C32: 10.3% of incidents in a travel lane
        factor = rng.uniform(0.35, 0.78)   # [DOC] Lindley: one lane blocked keeps 0.35-0.78
    else:
        factor = rng.uniform(0.81, 0.99)   # [DOC] Lindley: shoulder incident keeps 0.81-0.99
    return dur, factor


def sample_block_duration(rng):
    """Rows 2 / 5: normal(60, 20) truncated to [30, 120] min (same as v2)."""
    return min(max(rng.gauss(60.0, 20.0), 30.0), 120.0)


# ---------------------------------------------------------------------------
# 4. AGENTS
# ---------------------------------------------------------------------------
@dataclass
class Veh:
    vid: int
    is_av: bool
    node: int
    state: str = "idle"   # idle | driving | waiting | charging | charge_queue | stranded | done
    dest: int = None
    leg: str = None       # human: trip | AV: to_pickup, in_service, to_charger
    edge: tuple = None
    edge_left: float = 0.0
    range_mi: float = math.inf
    charge_until: float = 0.0
    req: dict = None
    # trip bookkeeping (human trip, or AV passenger leg)
    trip_start: float = 0.0
    trip_origin: int = None
    trip_ff: float = 0.0
    planned: list = None
    reroutes: int = 0
    stuck_min: float = 0.0
    wait_min: float = 0.0


class Sim:
    def __init__(self, p: Params, seed: int = 0, hazards_on: bool = True, profiles=None):
        self.p = p
        self.seed = seed
        self.hazards_on = hazards_on
        prof = profiles or load_profiles()
        dt = p.day_type
        self.h_share = prof[f"human_trips_{dt}"]
        self.h_vmt_share = prof[f"human_vmt_{dt}"]
        self.av_share = prof[f"av_trips_{dt}"]
        self.g = self._build_graph()
        self.t = 0
        self.haz_rng = random.Random(seed * 7919 + 11)
        self.fwy_edges = [ekey(u, v) for u, v, c in EDGES if c == "fwy"]
        self.all_edges = [ekey(u, v) for u, v, _ in EDGES]
        # static free-flow shortest times / miles (for delay measurement and range checks)
        self.ff_min = dict(nx.all_pairs_dijkstra_path_length(self.g, weight="ff"))
        # directed-edge state
        self.entries = defaultdict(deque)      # (u,v) -> entry minutes in last 60 min
        self.cap_events = defaultdict(list)    # (u,v) -> [(end, factor, row)]
        self.blocked = {}                      # undirected key -> (end, row)
        self.dark = {}                         # node -> (end, row)
        self.charging_at = defaultdict(set)    # node -> vids charging
        self.charge_queue = defaultdict(deque)
        self._route_t = -1
        # logs
        self.trip_log, self.av_log, self.event_log, self.charge_log, self.stranded = [], [], [], [], []
        self.hourly = [defaultdict(float) for _ in range(24)]
        self.vmt = {"human": 0.0, "av_pax": 0.0, "av_empty": 0.0}
        self.cls_delay, self.cls_miles = defaultdict(float), defaultdict(float)
        # demand (identical for a given seed regardless of hazards)
        self._make_demand(random.Random(seed * 7919 + 3))
        # AV fleet
        fl_rng = random.Random(seed * 7919 + 5)
        nodes = list(NODES)
        self.avs = []
        for i in range(p.n_av):
            v = Veh(10_000 + i, True, nodes[i % len(nodes)])
            v.range_mi = fl_rng.uniform(*p.av_start_range_mi)
            self.avs.append(v)
        self.humans = []          # active human vehicles
        self.pending = deque()    # AV requests waiting for a vehicle
        self.next_vid = 0

    # --- setup ---------------------------------------------------------------
    def _build_graph(self):
        g = nx.Graph()
        for n, name in NODES.items():
            g.add_node(n, name=name)
        for u, v, cls in EDGES:
            miles = haversine_mi(COORDS[u], COORDS[v]) * CIRCUITY
            ff = max(1, round(miles / self.p.ff_speed_mph[cls] * 60))  # whole minutes (1-min clock)
            g.add_edge(u, v, miles=miles, ff=ff, cls=cls)
        return g

    def _pick_od(self, rng):
        nodes = list(NODES)
        w = [self.p.node_weights.get(n, 1.0) for n in nodes] if self.p.node_weights else None
        o = rng.choices(nodes, weights=w)[0]
        rest = [n for n in nodes if n != o]
        wr = [self.p.node_weights.get(n, 1.0) for n in rest] if self.p.node_weights else None
        return o, rng.choices(rest, weights=wr)[0]

    def _make_demand(self, rng):
        def poisson(lam):
            # Knuth for small lam, normal approx for large
            if lam > 50:
                return max(0, round(rng.gauss(lam, math.sqrt(lam))))
            L, k, prod = math.exp(-lam), 0, rng.random()
            while prod > L:
                k += 1
                prod *= rng.random()
            return k

        self.human_demand, self.av_demand = defaultdict(list), defaultdict(list)
        for h in range(24):
            scale = self.p.weekend_trip_factor if self.p.day_type == "weekend" else 1.0
            for _ in range(poisson(self.p.human_trips_per_day * scale * self.h_share[h])):
                o, d = self._pick_od(rng)
                self.human_demand[h * 60 + rng.randrange(60)].append((o, d))
            for _ in range(poisson(self.p.av_requests_per_day * self.av_share[h])):
                o, d = self._pick_od(rng)
                self.av_demand[h * 60 + rng.randrange(60)].append((o, d))

    # --- network state ----------------------------------------------------------
    def cap_factor(self, u, v):
        if ekey(u, v) in self.blocked:
            return 0.0
        f = min((fac for _, fac, _ in self.cap_events[(u, v)]), default=1.0)
        if self.p.rain_day:
            f *= self.p.rain_capacity_factor
        return f

    def travel_time(self, u, v):
        ff = self.g.edges[u, v]["ff"]
        if not self.p.congestion:
            return float(ff)
        f = self.cap_factor(u, v)
        cap = self.p.capacity_vph[self.g.edges[u, v]["cls"]] * f
        q = len(self.entries[(u, v)])
        tti = 1 + self.p.bpr_alpha * (q / cap) ** self.p.bpr_beta
        return ff * min(tti, self.p.max_tti)

    def routes(self):
        """All-pairs fastest paths on open edges with current congested times (cached per minute)."""
        if self._route_t != self.t:
            dg = nx.DiGraph()
            dg.add_nodes_from(NODES)
            for u, v, _ in EDGES:
                if ekey(u, v) in self.blocked:
                    continue
                dg.add_edge(u, v, w=self.travel_time(u, v))
                dg.add_edge(v, u, w=self.travel_time(v, u))
            self._dist, self._paths = {}, {}
            for n in NODES:
                d, pth = nx.single_source_dijkstra(dg, n, weight="w")
                self._dist[n], self._paths[n] = d, pth
            self._route_t = self.t
        return self._dist, self._paths

    def path_miles(self, path):
        return sum(self.g.edges[a, b]["miles"] for a, b in zip(path, path[1:]))

    def working_chargers(self):
        return [c for c in self.p.chargers if c not in self.dark]

    def nearest_charger(self, node):
        dist, paths = self.routes()
        opts = [(dist[node][c], c) for c in self.working_chargers() if c in dist[node]]
        return min(opts)[1] if opts else None

    # --- hazards --------------------------------------------------------------------
    def update_hazards(self):
        t, h = self.t, self.t // 60 % 24
        for e, (end, _) in list(self.blocked.items()):
            if t >= end:
                del self.blocked[e]
        for de in list(self.cap_events):
            self.cap_events[de] = [x for x in self.cap_events[de] if x[0] > t]
        for n, (end, _) in list(self.dark.items()):
            if t >= end:
                del self.dark[n]
        for u, v, start, dur in self.p.forced_blocks:
            if t == start:
                self._block(ekey(u, v), dur, "forced")
        for n, start, dur in self.p.forced_outages:
            if t == start:
                self._dark(n, dur, "forced")
        if not self.hazards_on:
            return
        rng = self.haz_rng
        for row in self.p.hazards:
            if row in EDGE_HAZARDS:
                hz = EDGE_HAZARDS[row]
                edges = self.fwy_edges if hz["edges"] == "fwy" else self.all_edges
                tod = 24 * (self.h_vmt_share[h] if hz["driver"] == "human" else self.av_share[h])
                lam_h = hz["H"] / len(edges) * tod * (self.p.rain_incident_mult if self.p.rain_day else 1)
                p_min = 1 - math.exp(-lam_h / 60)
                for e in edges:
                    if rng.random() < p_min:
                        if hz["kind"] == "block":
                            if e not in self.blocked:
                                self._block(e, sample_block_duration(rng), row)
                        else:
                            dur, fac = sample_reduce_event(rng)
                            de = e if rng.random() < 0.5 else (e[1], e[0])  # one direction
                            self.cap_events[de].append((t + dur, fac, row))
                            self._log_event(row, de, t, dur, fac)
            elif row in NODE_HAZARDS:
                hz = NODE_HAZARDS[row]
                p_min = 1 - math.exp(-hz["per_year"] / 525_600)
                for n in NODES:
                    if n not in self.dark and rng.random() < p_min:
                        self._dark(n, rng.expovariate(1 / hz["mean_min"]), row)

    def _log_event(self, row, where, start, dur, factor, sep=" -> "):
        name = (f"{NODES[where[0]]}{sep}{NODES[where[1]]}" if isinstance(where, tuple) else NODES[where] + " (depot)")
        self.event_log.append(dict(row=row, where=name, start_min=start, duration_min=round(dur, 1),
                                   capacity_factor=round(factor, 2)))
        self.hourly[start // 60 % 24]["events_row_" + row] += 1

    def _block(self, e, dur, row):
        self.blocked[e] = (self.t + dur, row)
        self._log_event(row, e, self.t, dur, 0.0, sep=" - ")  # both directions

    def _dark(self, n, dur, row):
        self.dark[n] = (self.t + dur, row)
        self._log_event(row, n, self.t, dur, 0.0)
        for vid in list(self.charging_at[n]):        # interrupt sessions at the dark depot
            av = next(a for a in self.avs if a.vid == vid)
            self.charging_at[n].discard(vid)
            av.state = "idle"
        for av in [a for a in self.avs if a.state == "charge_queue" and a.node == n]:
            av.state = "idle"
        self.charge_queue[n].clear()

    # --- movement -------------------------------------------------------------------
    def start_leg(self, veh, dest, leg):
        veh.dest, veh.leg = dest, leg
        veh.trip_start, veh.trip_origin = self.t, veh.node
        veh.trip_ff = self.ff_min[veh.node][dest]
        veh.planned = nx.dijkstra_path(self.g, veh.node, dest, weight="ff")
        veh.reroutes, veh.stuck_min, veh.wait_min = 0, 0.0, 0.0
        if veh.node == dest:
            self.leg_done(veh)
        else:
            self.take_next_edge(veh)

    def take_next_edge(self, veh):
        _, paths = self.routes()
        route = paths[veh.node].get(veh.dest)
        if route is None:
            veh.state = "waiting"
            return
        exp = veh.planned[veh.planned.index(veh.node):] if veh.node in veh.planned else None
        if route != exp:
            veh.reroutes += 1
            veh.planned = route
        u, v = veh.node, route[1]
        tt = self.travel_time(u, v)
        self.entries[(u, v)].append(self.t)
        hr = self.hourly[self.t // 60 % 24]
        ed = self.g.edges[u, v]
        hr["tti_sum"] += tt / ed["ff"]
        hr["tti_n"] += 1
        self.cls_delay[ed["cls"]] += tt - ed["ff"]
        self.cls_miles[ed["cls"]] += ed["miles"]
        veh.edge, veh.edge_left, veh.state = (u, v), tt, "driving"

    def advance(self, veh):
        if ekey(*veh.edge) in self.blocked:
            veh.stuck_min += 1
            return
        veh.edge_left -= 1
        if veh.edge_left > 0.5:   # arrive on the nearest whole minute
            return
        u, v = veh.edge
        miles = self.g.edges[u, v]["miles"]
        if veh.is_av:
            veh.range_mi -= miles
            self.vmt["av_pax" if veh.leg == "in_service" else "av_empty"] += miles
        else:
            self.vmt["human"] += miles
        veh.node, veh.edge = v, None
        if veh.is_av and veh.range_mi <= 0:
            veh.state = "stranded"
            self.stranded.append(dict(av=veh.vid, minute=self.t, node=NODES[v], leg=veh.leg))
            if veh.req:
                self._log_request(veh.req, served=False, reason="vehicle stranded")
            return
        if v == veh.dest:
            self.leg_done(veh)
        else:
            self.take_next_edge(veh)

    def leg_done(self, veh):
        actual = self.t - veh.trip_start
        if not veh.is_av:
            self.trip_log.append(dict(
                origin=NODES[veh.trip_origin], dest=NODES[veh.node], start_min=veh.trip_start,
                end_min=self.t, actual_min=actual, freeflow_min=veh.trip_ff,
                delay_min=actual - veh.trip_ff, reroutes=veh.reroutes,
                stuck_on_blocked_edge_min=veh.stuck_min, waited_no_route_min=veh.wait_min))
            hr = self.hourly[veh.trip_start // 60 % 24]
            hr["human_done"] += 1
            hr["human_delay"] += actual - veh.trip_ff
            veh.state = "done"
            return
        if veh.leg == "to_pickup":
            r = veh.req
            r["pickup_min"] = self.t
            self.start_leg(veh, r["dest"], "in_service")
        elif veh.leg == "in_service":
            r = veh.req
            r.update(dropoff_min=self.t, ride_min=actual, ride_ff_min=veh.trip_ff,
                     ride_delay_min=actual - veh.trip_ff)
            self._log_request(r, served=True)
            veh.req = None
            self.become_idle(veh)
        elif veh.leg == "to_charger":
            self.try_charge(veh)

    # --- AV logic ----------------------------------------------------------------
    def become_idle(self, av):
        av.state, av.leg, av.dest = "idle", None, None
        if av.range_mi < self.p.av_charge_threshold_mi:
            self.send_to_charger(av)

    def send_to_charger(self, av):
        c = self.nearest_charger(av.node)
        if c is None:
            av.state = "idle"  # no working charger reachable; retry each minute
            return
        self.start_leg(av, c, "to_charger")

    def try_charge(self, av):
        n = av.node
        if n in self.dark or n not in self.p.chargers:
            self.send_to_charger(av)
            return
        ports = self.p.ports_per_charger
        if ports is not None and len(self.charging_at[n]) >= ports:
            av.state = "charge_queue"
            self.charge_queue[n].append(av.vid)
            return
        rate = self.p.charge_kwh_per_min * self.p.mi_per_kwh
        need = max(self.p.av_max_range_mi - av.range_mi, 0)
        av.state, av.charge_until = "charging", self.t + max(1, math.ceil(need / rate))
        self.charging_at[n].add(av.vid)
        self.charge_log.append(dict(av=av.vid, node=NODES[n], start_min=self.t,
                                    range_before=round(av.range_mi, 1)))

    def step_charging(self, av):
        rate = self.p.charge_kwh_per_min * self.p.mi_per_kwh
        av.range_mi = min(self.p.av_max_range_mi, av.range_mi + rate)
        if self.t >= av.charge_until:
            n = av.node
            self.charging_at[n].discard(av.vid)
            if self.charge_queue[n]:
                nxt_id = self.charge_queue[n].popleft()
                nxt = next(a for a in self.avs if a.vid == nxt_id)
                self.try_charge(nxt)
            av.state, av.leg = "idle", None

    def dispatch(self):
        dist, paths = self.routes()
        still = deque()
        while self.pending:
            r = self.pending.popleft()
            if self.t - r["request_min"] > self.p.av_max_wait_min:
                self._log_request(r, served=False, reason="no vehicle within max wait")
                continue
            o, d = r["origin"], r["dest"]
            best = None
            if d not in dist[o]:
                still.append(r)
                continue
            c = self.nearest_charger(d)
            # range needed after the drop-off: reach the nearest working charger + reserve, or, if no
            # depot is working, keep the normal charge threshold in hand [ASSUMPTION]
            after = (self.path_miles(paths[d][c]) + self.p.av_reserve_mi) if c is not None \
                else self.p.av_charge_threshold_mi
            trip_mi = self.path_miles(paths[o][d]) + after
            for av in self.avs:
                if av.state != "idle" or o not in dist[av.node]:
                    continue
                need = self.path_miles(paths[av.node][o]) + trip_mi
                if av.range_mi < need:
                    continue
                cand = (dist[av.node][o], av.vid, av)
                if best is None or cand[:2] < best[:2]:
                    best = cand
            if best is None:
                still.append(r)
                continue
            av = best[2]
            r["assign_min"] = self.t
            r["av"] = av.vid
            av.req = r
            self.start_leg(av, o, "to_pickup")
        self.pending = still

    def _log_request(self, r, served, reason=""):
        row = dict(request_min=r["request_min"], origin=NODES[r["origin"]], dest=NODES[r["dest"]],
                   served=served, reason=reason, av=r.get("av"),
                   wait_min=(r["pickup_min"] - r["request_min"]) if "pickup_min" in r and served else None,
                   ride_min=r.get("ride_min"), ride_delay_min=r.get("ride_delay_min"))
        self.av_log.append(row)
        hr = self.hourly[r["request_min"] // 60 % 24]
        hr["av_served" if served else "av_unserved"] += 1
        if served:
            hr["av_wait"] += row["wait_min"]

    # --- main loop -------------------------------------------------------------------
    def step(self):
        t = self.t
        for de in list(self.entries):           # roll the 60-min flow window
            q = self.entries[de]
            while q and q[0] <= t - 60:
                q.popleft()
        self.update_hazards()
        # vehicles already on the road move first
        for veh in self.humans + self.avs:
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
        # new demand this minute (starts moving next minute, so free-flow trips take exactly ff)
        for o, d in self.human_demand.get(t, []):
            veh = Veh(self.next_vid, False, o)
            self.next_vid += 1
            self.humans.append(veh)
            self.hourly[t // 60]["human_dep"] += 1
            self.start_leg(veh, d, "trip")
        for o, d in self.av_demand.get(t, []):
            self.pending.append(dict(request_min=t, origin=o, dest=d))
            self.hourly[t // 60]["av_req"] += 1
        self.dispatch()
        self.t += 1

    def run(self):
        while self.t < self.p.sim_minutes:
            self.step()
        return self

    # --- outputs ------------------------------------------------------------------------
    def summary(self):
        trips = self.trip_log
        n = len(trips)
        served = [r for r in self.av_log if r["served"]]
        waits = sorted(r["wait_min"] for r in served)
        tot_vmt = sum(self.vmt.values())
        av_vmt = self.vmt["av_pax"] + self.vmt["av_empty"]
        by_row = defaultdict(int)
        for e in self.event_log:
            by_row[e["row"]] += 1
        return dict(
            human_trips_completed=n,
            human_trips_unfinished=len(self.humans),
            human_mean_trip_min=round(sum(r["actual_min"] for r in trips) / n, 2) if n else 0,
            human_total_delay_min=round(sum(r["delay_min"] for r in trips), 1),
            human_trips_rerouted=sum(r["reroutes"] > 0 for r in trips),
            human_min_stuck_on_blocked_edges=sum(r["stuck_on_blocked_edge_min"] for r in trips),
            av_requests=sum(len(v) for v in self.av_demand.values()),
            av_served=len(served),
            av_unserved=sum(not r["served"] for r in self.av_log),
            av_open_at_end_of_day=sum(len(v) for v in self.av_demand.values()) - len(self.av_log),
            av_mean_wait_min=round(sum(waits) / len(waits), 2) if waits else 0,
            av_p95_wait_min=waits[int(0.95 * (len(waits) - 1))] if waits else 0,
            av_ride_delay_min=round(sum(r["ride_delay_min"] for r in served), 1),
            av_empty_mile_share=round(self.vmt["av_empty"] / av_vmt, 3) if av_vmt else 0,
            av_share_of_vmt=round(av_vmt / tot_vmt, 4) if tot_vmt else 0,
            av_charge_events=len(self.charge_log),
            av_stranded=len(self.stranded),
            fwy_delay_min_per_mi=round(self.cls_delay["fwy"] / self.cls_miles["fwy"], 3) if self.cls_miles["fwy"] else 0,
            peak_hour_tti=round(max(h["tti_sum"] / h["tti_n"] for h in self.hourly if h["tti_n"]), 3),
            events=dict(sorted(by_row.items())),
        )

    def hourly_rows(self):
        rows = []
        for h, d in enumerate(self.hourly):
            rows.append(dict(
                hour=h, human_departures=int(d["human_dep"]), av_requests=int(d["av_req"]),
                mean_tti=round(d["tti_sum"] / d["tti_n"], 3) if d["tti_n"] else None,
                human_mean_delay_min=round(d["human_delay"] / d["human_done"], 2) if d["human_done"] else None,
                av_served=int(d["av_served"]), av_unserved=int(d["av_unserved"]),
                av_mean_wait_min=round(d["av_wait"] / d["av_served"], 2) if d["av_served"] else None,
                **{k: int(v) for k, v in d.items() if k.startswith("events_row_")}))
        return rows

    def write_logs(self, prefix):
        hrs = self.hourly_rows()
        base_keys = [k for k in hrs[0] if not k.startswith("events_row_")]
        keys = base_keys + sorted({k for r in hrs for k in r if k.startswith("events_row_")})
        sets = [("trips", self.trip_log, None), ("av_requests", self.av_log, None),
                ("events", self.event_log, None), ("charges", self.charge_log, None),
                ("hourly", hrs, keys)]
        for name, rows, fields in sets:
            if not rows:
                continue
            with open(f"{prefix}_{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields or list(rows[0]), restval=0)
                w.writeheader()
                w.writerows(rows)


# ---------------------------------------------------------------------------
# 5. CLI
# ---------------------------------------------------------------------------
def parse_force(s):      # "5-6@480+60"
    e, rest = s.split("@")
    u, v = map(int, e.split("-"))
    start, dur = rest.split("+")
    return (u, v, int(start), float(dur))


def parse_outage(s):     # "6@1020+120"
    n, rest = s.split("@")
    start, dur = rest.split("+")
    return (int(n), int(start), float(dur))


def fmt(label, s):
    return label + "\n" + "\n".join(f"  {k:34s} {v}" for k, v in s.items())


def print_hourly(sim_b, sim_h):
    hb, hh = sim_b.hourly_rows(), sim_h.hourly_rows()
    print(f"\n  {'hour':>4s} {'human':>6s} {'AVreq':>6s} {'TTI base':>9s} {'TTI haz':>8s} "
          f"{'delay base':>10s} {'delay haz':>9s} {'AV wait haz':>11s} {'AV unserved':>11s}")
    for b, h in zip(hb, hh):
        f = lambda x, w: f"{x:{w}.2f}" if isinstance(x, (int, float)) else f"{'-':>{w}s}"
        print(f"  {b['hour']:4d} {b['human_departures']:6d} {b['av_requests']:6d} {f(b['mean_tti'], 9)} "
              f"{f(h['mean_tti'], 8)} {f(b['human_mean_delay_min'], 10)} {f(h['human_mean_delay_min'], 9)} "
              f"{f(h['av_mean_wait_min'], 11)} {h['av_unserved']:11d}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--day-type", choices=["weekday", "weekend"], default="weekday")
    ap.add_argument("--force", action="append", default=[], help="block edge: u-v@start_min+dur_min")
    ap.add_argument("--outage", action="append", default=[], help="charger dark: node@start_min+dur_min")
    ap.add_argument("--rain", action="store_true", help="rain day (row 1b)")
    ap.add_argument("--hazards", default="1,2,4,5,9,10", help="comma list of table rows to sample")
    ap.add_argument("--no-congestion", action="store_true")
    ap.add_argument("--sweep", action="store_true", help="block each edge alone for 60 min")
    ap.add_argument("--sweep-start", type=int, default=480)
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--human-trips", type=int)
    ap.add_argument("--av-requests", type=int)
    ap.add_argument("--n-av", type=int)
    ap.add_argument("--ports", type=int, help="charging ports per depot (default unlimited)")
    ap.add_argument("--chargers", help="comma list of depot nodes (default: all 10)")
    ap.add_argument("--logs", default="run")
    a = ap.parse_args()

    def P(**kw):
        p = Params(day_type=a.day_type, congestion=not a.no_congestion, rain_day=a.rain,
                   hazards=tuple(x for x in a.hazards.split(",") if x), ports_per_charger=a.ports)
        if a.chargers:
            p.chargers = frozenset(int(x) for x in a.chargers.split(","))
        if a.human_trips:
            p.human_trips_per_day = a.human_trips
        if a.av_requests:
            p.av_requests_per_day = a.av_requests
        if a.n_av:
            p.n_av = a.n_av
        for k, v in kw.items():
            setattr(p, k, v)
        return p

    profiles = load_profiles()

    if a.calibrate:
        s = Sim(P(congestion=False), a.seed, hazards_on=False, profiles=profiles)
        flows = defaultdict(lambda: [0] * 24)
        orig = s.take_next_edge

        def counting(veh):
            orig(veh)
            if veh.state == "driving":
                flows[veh.edge][s.t // 60] += 1
        s.take_next_edge = counting
        s.run()
        print(f"Free-flow run, no hazards, {a.day_type}, seed {a.seed}: peak hourly flow per direction")
        cap = Params().capacity_vph
        rows = []
        for (u, v), f in flows.items():
            cls = s.g.edges[u, v]["cls"]
            pk = max(f)
            rows.append((pk / cap[cls], f"{NODES[u]} -> {NODES[v]}", cls, pk, f.index(pk)))
        for vc, name, cls, pk, h in sorted(rows, reverse=True):
            print(f"  {name:34s} {cls}  peak {pk:4d} veh/h at {h:02d}:00   v/c at default capacity {vc:.2f}")
        return

    if a.days:
        keys = ["human_trips_completed", "human_total_delay_min", "human_trips_rerouted",
                "human_min_stuck_on_blocked_edges", "av_served", "av_unserved", "av_mean_wait_min",
                "av_ride_delay_min", "av_share_of_vmt", "av_charge_events", "av_stranded", "peak_hour_tti"]
        acc = {k: [0.0, 0.0] for k in keys}
        ev = defaultdict(float)
        for d in range(a.days):
            sb = Sim(P(), d, hazards_on=False, profiles=profiles).run().summary()
            sh = Sim(P(), d, hazards_on=True, profiles=profiles).run().summary()
            for k in keys:
                acc[k][0] += sb[k] / a.days
                acc[k][1] += sh[k] / a.days
            for r, c in sh["events"].items():
                ev[r] += c / a.days
        print(f"AVERAGE OVER {a.days} {a.day_type.upper()} DAYS (seeds 0..{a.days - 1})"
              f"{', RAIN' if a.rain else ''}")
        print(f"  {'metric':34s} {'baseline':>10s} {'hazards':>10s} {'difference':>11s}")
        for k in keys:
            print(f"  {k:34s} {acc[k][0]:10.3f} {acc[k][1]:10.3f} {acc[k][1] - acc[k][0]:11.3f}")
        print("  events per day by table row: " + ", ".join(f"row {r}: {c:.3f}" for r, c in sorted(ev.items())))
        return

    base = Sim(P(), a.seed, hazards_on=False, profiles=profiles).run()
    sb = base.summary()
    print(fmt(f"BASELINE (recurring congestion only), {a.day_type}, seed {a.seed}", sb))

    if a.sweep:
        print(f"\nSINGLE-EDGE SWEEP: each edge blocked 60 min from minute {a.sweep_start}, no other hazards")
        print(f"  {'edge':34s} {'cls':4s} {'+delay_min':>10s} {'rerouted':>9s} {'stuck_min':>10s} "
              f"{'+AV unserved':>12s} {'+AV wait':>9s}")
        out = []
        for u, v, cls in EDGES:
            s = Sim(P(forced_blocks=[(u, v, a.sweep_start, 60)]), a.seed, hazards_on=False,
                    profiles=profiles).run().summary()
            out.append((s["human_total_delay_min"] - sb["human_total_delay_min"],
                        f"{NODES[u]} - {NODES[v]}", cls, s["human_trips_rerouted"],
                        s["human_min_stuck_on_blocked_edges"], s["av_unserved"] - sb["av_unserved"],
                        s["av_mean_wait_min"] - sb["av_mean_wait_min"]))
        for dl, name, cls, rr, st, au, aw in sorted(out, reverse=True):
            print(f"  {name:34s} {cls:4s} {dl:10.1f} {rr:9d} {st:10.0f} {au:12d} {aw:9.2f}")
        return

    forced = [parse_force(x) for x in a.force]
    outages = [parse_outage(x) for x in a.outage]
    scenario = bool(forced or outages)
    sim = Sim(P(forced_blocks=forced, forced_outages=outages), a.seed,
              hazards_on=not scenario, profiles=profiles).run()
    label = "FORCED SCENARIO" if scenario else "STOCHASTIC HAZARDS (rows " + a.hazards + ")"
    print("\n" + fmt(f"{label}, {a.day_type}, seed {a.seed}", sim.summary()))
    print_hourly(base, sim)
    big = [e for e in sim.event_log if e["row"] not in ("1", "4")]
    print(f"\nBlockages and outages ({len(big)}; rows 1/4 reduced-capacity events are in the CSV):")
    for e in big or [{"none": "this day"}]:
        print("  ", e)
    sim.write_logs(a.logs)


if __name__ == "__main__":
    main()
