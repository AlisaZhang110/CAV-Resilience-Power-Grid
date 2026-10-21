"""
Project #4 - 10-node AV/HV traffic simulation, failure mode #2 only
=====================================================================

Failure mode represented: Failure Mode Table row 2
    "Traffic incident - human driver", type = edge, severity = mid (no capacity)
    -> one edge fully blocked for a sampled duration.

What is taken directly from the source files (marked [DOC]) vs. what is an
assumption made for this prototype (marked [ASSUMPTION]) is labelled inline.

Run:
    python av_traffic_sim.py                 # baseline vs stochastic traffic, one day
    python av_traffic_sim.py --seed 7        # different random day
    python av_traffic_sim.py --sweep         # block each edge once (60 min @ 08:00)
    python av_traffic_sim.py --force 5-6@480+60   # block Culver City-Downtown at 08:00 for 60 min
    python av_traffic_sim.py --days 200      # average of 200 independent days, baseline vs traffic

Each run also writes CSV logs: <prefix>_trips.csv, _blocks.csv, _charges.csv (--logs sets prefix).
Requires: networkx.
"""

import argparse
import csv
import math
import random
from dataclasses import dataclass, field

import networkx as nx

# ---------------------------------------------------------------------------
# 1. NETWORK  [DOC: Project_4 notes, page 5 hand-drawn graph]
# ---------------------------------------------------------------------------
# Node numbers are the blue numbers on the sketch. (C) = charging station.
NODES = {
    1: "Santa Monica",
    2: "Sawtelle",
    3: "West Hollywood",
    4: "LAX",
    5: "Culver City",
    6: "Downtown LA",
    7: "Playa del Rey",
    8: "Mid-City",
    9: "Hollywood",
    10: "Pasadena",
}
# [USER] every node is a charger. (Notes, page 5, originally fixed Nc = {1, 2, 4, 5};
# set CHARGERS = {1, 2, 4, 5} to go back to that.)
CHARGERS = set(NODES)

# 17 undirected edges, exactly as drawn. (The notes text says "18 cases" for
# edge failure; the drawing itself has 17 lines.)
EDGES = [
    (1, 2),   # Santa Monica - Sawtelle
    (2, 3),   # Sawtelle - West Hollywood
    (3, 9),   # West Hollywood - Hollywood
    (9, 10),  # Hollywood - Pasadena
    (1, 5),   # Santa Monica - Culver City
    (1, 7),   # Santa Monica - Playa del Rey
    (2, 5),   # Sawtelle - Culver City
    (3, 5),   # West Hollywood - Culver City
    (5, 6),   # Culver City - Downtown LA
    (5, 4),   # Culver City - LAX
    (5, 8),   # Culver City - Mid-City
    (5, 7),   # Culver City - Playa del Rey
    (4, 8),   # LAX - Mid-City
    (8, 9),   # Mid-City - Hollywood
    (8, 6),   # Mid-City - Downtown LA
    (9, 6),   # Hollywood - Downtown LA
    (6, 10),  # Downtown LA - Pasadena
]

# Edge lengths: the sketch has no distances, so these are
# [ASSUMPTION] straight-line distance between approximate neighbourhood
# centroids x a road circuity factor. Replace with real road distances
# (e.g. Google/OSRM route lengths) when available.
COORDS = {  # (lat, lon), approximate centroids
    1: (34.0195, -118.4912),
    2: (34.0390, -118.4430),
    3: (34.0900, -118.3617),
    4: (33.9416, -118.4085),
    5: (34.0211, -118.3965),
    6: (34.0522, -118.2437),
    7: (33.9570, -118.4440),
    8: (34.0420, -118.3550),
    9: (34.0928, -118.3287),
    10: (34.1478, -118.1445),
}
CIRCUITY = 1.3          # [ASSUMPTION] road distance / straight-line distance
AVG_SPEED_MPH = 25.0    # [ASSUMPTION] free-flow average urban speed


def haversine_mi(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def build_graph():
    g = nx.Graph()
    for n, name in NODES.items():
        g.add_node(n, name=name, charger=(n in CHARGERS))
    for u, v in EDGES:
        miles = haversine_mi(COORDS[u], COORDS[v]) * CIRCUITY
        # whole minutes so the 1-minute simulation clock reproduces free-flow times exactly
        g.add_edge(u, v, miles=miles, minutes=max(1, round(miles / AVG_SPEED_MPH * 60)))
    return g


def ekey(u, v):
    return (u, v) if u < v else (v, u)


# ---------------------------------------------------------------------------
# 2. PARAMETERS
# ---------------------------------------------------------------------------
@dataclass
class Params:
    sim_minutes: int = 24 * 60     # [DOC] notes Week 4: "simulation = 24 time steps (1 day)"; run at 1-min resolution
    n_cars: int = 100              # [USER]
    n_av: int = 5                  # [USER]
    cars_per_node: int = 10        # [USER]
    dwell_min: float = 60.0        # [USER] stop for one hour at destination
    av_charge_threshold_mi: float = 50.0   # [USER]
    av_charge_min: float = 30.0            # [USER] charge 0.5 h
    # Waymo Jaguar I-PACE numbers [DOC: notes "Waymo Number Breakdown"]
    av_max_range_mi: float = 180.0         # upper end of "120-180 mi range"
    charge_kwh_per_min: float = 1.8        # "1.8 kWh per minute"
    mi_per_kwh: float = 3.5                # "3.5 mi/kWh"
    av_start_range_mi: tuple = (60.0, 180.0)   # [ASSUMPTION] uniform initial range
    # Failure mode #2 [DOC: Failure_Mode_Table.xlsx, row 2, column R]
    #   P per hour PER EDGE after area scaling = 0.002307995 (H9 / 9 freeway edges)
    p_block_per_edge_per_hour: float = 0.002307995058
    # Duration [USER] normal, mean 60 min. [DOC] row 2 duration "0.5-2 h, central ~1 h"
    block_mean_min: float = 60.0
    block_sd_min: float = 20.0             # [ASSUMPTION] puts 0.5-2 h at about +/-1.5 sd
    block_min_min: float = 30.0            # [DOC] truncate to the row-2 range 0.5 h ...
    block_max_min: float = 120.0           # ... to 2 h
    stochastic_traffic: bool = True
    forced_blocks: list = field(default_factory=list)  # [(u, v, start_min, duration_min)]


# ---------------------------------------------------------------------------
# 3. AGENTS
# ---------------------------------------------------------------------------
@dataclass
class Car:
    cid: int
    is_av: bool
    node: int
    rng: random.Random
    range_mi: float = math.inf
    state: str = "idle"          # idle | driving | dwell | charging | waiting
    dest: int = None
    purpose: str = "trip"        # trip | to_charger
    edge: tuple = None           # (u, v) currently being driven
    edge_left: float = 0.0       # minutes left on current edge
    busy_until: float = 0.0
    # current-trip bookkeeping
    trip_start: float = 0.0
    trip_origin: int = None
    trip_ff_min: float = 0.0
    trip_reroutes: int = 0
    trip_stuck_min: float = 0.0
    trip_wait_min: float = 0.0
    trip_planned_path: list = None


class Sim:
    def __init__(self, p: Params, seed: int = 0):
        self.p = p
        self.g = build_graph()
        self.t = 0
        self.traffic_rng = random.Random(seed * 1000 + 1)
        setup_rng = random.Random(seed * 1000 + 2)
        # per-minute block probability from the hourly probability
        lam_h = -math.log(1 - p.p_block_per_edge_per_hour)
        self.p_block_per_min = 1 - math.exp(-lam_h / 60)
        self.blocked = {}           # edge -> minute it reopens
        self.block_log = []
        self.trip_log = []
        self.charge_log = []
        self.stranded = []
        # free-flow shortest times for delay measurement
        self.ff = dict(nx.all_pairs_dijkstra_path_length(self.g, weight="minutes"))
        # spawn 10 cars per node, pick 5 at random to be AVs
        av_ids = set(setup_rng.sample(range(p.n_cars), p.n_av))
        self.cars = []
        cid = 0
        for n in NODES:
            for _ in range(p.cars_per_node):
                car = Car(cid, cid in av_ids, n, random.Random(seed * 1000 + 100 + cid))
                if car.is_av:
                    car.range_mi = setup_rng.uniform(*p.av_start_range_mi)
                self.cars.append(car)
                cid += 1

    # --- network state --------------------------------------------------
    def open_graph(self):
        h = self.g.copy()
        h.remove_edges_from(list(self.blocked))
        return h

    def update_traffic(self):
        # reopen
        for e, until in list(self.blocked.items()):
            if self.t >= until:
                del self.blocked[e]
        # forced blocks (scenario mode)
        for u, v, start, dur in self.p.forced_blocks:
            if self.t == start:
                self._block(ekey(u, v), dur, forced=True)
        # stochastic blocks: each open edge asks "am I going to fail this minute?"
        if self.p.stochastic_traffic:
            for u, v in self.g.edges:
                e = ekey(u, v)
                if e not in self.blocked and self.traffic_rng.random() < self.p_block_per_min:
                    d = self.traffic_rng.gauss(self.p.block_mean_min, self.p.block_sd_min)
                    d = min(max(d, self.p.block_min_min), self.p.block_max_min)
                    self._block(e, d)

    def _block(self, e, dur, forced=False):
        self.blocked[e] = self.t + dur
        self.block_log.append(dict(edge=f"{NODES[e[0]]} - {NODES[e[1]]}", start_min=self.t,
                                   duration_min=round(dur, 1), forced=forced))

    def path(self, src, dst):
        try:
            return nx.dijkstra_path(self.open_graph(), src, dst, weight="minutes")
        except nx.NetworkXNoPath:
            return None

    # --- car decisions ---------------------------------------------------
    def start_next_activity(self, car):
        p = self.p
        if car.is_av and car.range_mi < p.av_charge_threshold_mi:
            if car.node in CHARGERS:
                self.begin_charge(car)
                return
            # [ASSUMPTION] head to the nearest reachable charger (by current travel time)
            h = self.open_graph()
            dist = nx.single_source_dijkstra_path_length(h, car.node, weight="minutes")
            options = [(dist[c], c) for c in CHARGERS if c in dist]
            if not options:
                car.dest = None
                car.state = "waiting"
                return
            car.purpose, car.dest = "to_charger", min(options)[1]
        else:
            car.purpose = "trip"
            car.dest = car.rng.choice([n for n in NODES if n != car.node])  # [USER] random destination
        car.trip_start, car.trip_origin = self.t, car.node
        car.trip_ff_min = self.ff[car.node][car.dest]
        car.trip_reroutes = 0
        car.trip_stuck_min = car.trip_wait_min = 0.0
        car.trip_planned_path = nx.dijkstra_path(self.g, car.node, car.dest, weight="minutes")
        self.take_next_edge(car)

    def take_next_edge(self, car):
        route = self.path(car.node, car.dest)
        if route is None:
            car.state = "waiting"  # no open route: wait at node, retry next minute
            return
        planned = car.trip_planned_path
        expected = planned[planned.index(car.node):] if planned and car.node in planned else None
        if route != expected:          # route differs from the free-flow / last plan -> rerouted
            car.trip_reroutes += 1
            car.trip_planned_path = route
        nxt = route[1]
        car.edge = (car.node, nxt)
        car.edge_left = self.g.edges[car.node, nxt]["minutes"]
        car.state = "driving"

    def begin_charge(self, car):
        car.state = "charging"
        car.busy_until = self.t + self.p.av_charge_min
        before = car.range_mi
        added = self.p.charge_kwh_per_min * self.p.av_charge_min * self.p.mi_per_kwh
        car.range_mi = min(self.p.av_max_range_mi, car.range_mi + added)
        self.charge_log.append(dict(car=car.cid, node=NODES[car.node], start_min=self.t,
                                    range_before=round(before, 1), range_after=round(car.range_mi, 1)))

    def arrive(self, car):
        u, v = car.edge
        if car.is_av:
            car.range_mi -= self.g.edges[u, v]["miles"]
            if car.range_mi <= 0:
                self.stranded.append((car.cid, self.t, NODES[v]))
        car.node, car.edge = v, None
        if v != car.dest:
            self.take_next_edge(car)
            return
        actual = self.t - car.trip_start
        self.trip_log.append(dict(
            car=car.cid, av=car.is_av, purpose=car.purpose,
            origin=NODES[car.trip_origin], dest=NODES[v], start_min=car.trip_start,
            end_min=self.t, actual_min=round(actual, 1), freeflow_min=round(car.trip_ff_min, 1),
            delay_min=round(actual - car.trip_ff_min, 1), reroutes=car.trip_reroutes,
            stuck_on_blocked_edge_min=car.trip_stuck_min, waited_no_route_min=car.trip_wait_min))
        if car.purpose == "to_charger":
            self.begin_charge(car)
        else:
            car.state = "dwell"
            car.busy_until = self.t + self.p.dwell_min

    # --- main loop -------------------------------------------------------
    def step(self):
        self.update_traffic()
        for car in self.cars:
            if car.state == "idle":
                self.start_next_activity(car)
            elif car.state in ("dwell", "charging"):
                if self.t >= car.busy_until:
                    self.start_next_activity(car)
            elif car.state == "waiting":
                car.trip_wait_min += 1
                if car.dest is None:          # was waiting for a reachable charger
                    self.start_next_activity(car)
                else:
                    self.take_next_edge(car)
            elif car.state == "driving":
                if ekey(*car.edge) in self.blocked:
                    car.trip_stuck_min += 1   # caught on the blocked edge: no progress
                    continue
                car.edge_left -= 1
                if car.edge_left <= 0:
                    self.arrive(car)
        self.t += 1

    def run(self):
        while self.t < self.p.sim_minutes:
            self.step()
        return self

    # --- outputs ---------------------------------------------------------
    def summary(self):
        trips = [r for r in self.trip_log if r["purpose"] == "trip"]
        n = len(trips)
        delayed = [r for r in trips if r["delay_min"] > 1]
        return dict(
            completed_trips=n,
            av_trips=sum(r["av"] for r in trips),
            mean_trip_min=round(sum(r["actual_min"] for r in trips) / n, 2) if n else 0,
            total_delay_min=round(sum(max(r["delay_min"], 0) for r in trips), 1),
            trips_delayed_gt_1min=len(delayed),
            trips_rerouted=sum(r["reroutes"] > 0 for r in trips),
            minutes_stuck_on_blocked_edges=sum(r["stuck_on_blocked_edge_min"] for r in trips),
            edge_block_events=len(self.block_log),
            av_charge_events=len(self.charge_log),
            av_stranded=len(self.stranded),
        )

    def write_logs(self, prefix):
        for name, rows in (("trips", self.trip_log), ("blocks", self.block_log),
                           ("charges", self.charge_log)):
            if not rows:
                continue
            with open(f"{prefix}_{name}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)


# ---------------------------------------------------------------------------
# 4. CLI
# ---------------------------------------------------------------------------
def parse_force(s):
    # "5-6@480+60" -> (5, 6, 480, 60)
    e, rest = s.split("@")
    u, v = map(int, e.split("-"))
    start, dur = rest.split("+")
    return (u, v, int(start), float(dur))


def fmt_summary(label, s):
    keys = list(s)
    return label + "\n" + "\n".join(f"  {k:32s} {s[k]}" for k in keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--force", action="append", default=[], help="u-v@start_min+duration_min")
    ap.add_argument("--sweep", action="store_true", help="block each edge once, 60 min at 08:00")
    ap.add_argument("--logs", default="run", help="prefix for CSV logs")
    ap.add_argument("--days", type=int, default=0, help="run N independent days, report averages")
    a = ap.parse_args()

    if a.days:
        keys = ["completed_trips", "total_delay_min", "trips_rerouted",
                "minutes_stuck_on_blocked_edges", "edge_block_events", "av_charge_events", "av_stranded"]
        acc = {k: [0.0, 0.0] for k in keys}  # [baseline, traffic]
        for d in range(a.days):
            sb = Sim(Params(stochastic_traffic=False), d).run().summary()
            st = Sim(Params(), d).run().summary()
            for k in keys:
                acc[k][0] += sb[k] / a.days
                acc[k][1] += st[k] / a.days
        print(f"AVERAGE OVER {a.days} DAYS (seeds 0..{a.days - 1})")
        print(f"  {'metric':32s} {'baseline':>10s} {'traffic':>10s}")
        for k in keys:
            print(f"  {k:32s} {acc[k][0]:10.2f} {acc[k][1]:10.2f}")
        return

    base = Sim(Params(stochastic_traffic=False), a.seed).run()
    sb = base.summary()
    print(fmt_summary(f"BASELINE (no traffic), seed {a.seed}", sb))

    if a.sweep:
        print("\nSINGLE-EDGE SWEEP: each edge blocked 60 min starting 08:00, no other failures")
        print(f"  {'edge':34s} {'trips':>6s} {'delay_min':>10s} {'rerouted':>9s} {'stuck_min':>10s}")
        for u, v in EDGES:
            s = Sim(Params(stochastic_traffic=False, forced_blocks=[(u, v, 480, 60)]), a.seed).run().summary()
            print(f"  {NODES[u] + ' - ' + NODES[v]:34s} {s['completed_trips']:6d} "
                  f"{s['total_delay_min'] - sb['total_delay_min']:10.1f} {s['trips_rerouted']:9d} "
                  f"{s['minutes_stuck_on_blocked_edges']:10.0f}")
        return

    forced = [parse_force(x) for x in a.force]
    sim = Sim(Params(stochastic_traffic=not forced, forced_blocks=forced), a.seed).run()
    label = "FORCED BLOCK" if forced else "STOCHASTIC TRAFFIC (failure mode #2)"
    print("\n" + fmt_summary(f"{label}, seed {a.seed}", sim.summary()))
    print("\nEdge blockages:")
    for b in sim.block_log or [{"edge": "none this day"}]:
        print("  ", b)
    print("\nAV charging events:")
    for c in sim.charge_log or [{"car": "none"}]:
        print("  ", c)
    sim.write_logs(a.logs)


if __name__ == "__main__":
    main()
