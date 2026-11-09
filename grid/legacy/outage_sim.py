"""
Line-level Markov outage simulation on the 33-bus feeder.

markov_outages.py treats each depot as one up/down switch. Here, every feeder
line has its own up/down Markov process, and the feeder topology decides which
buses (and therefore which depots) lose power. Depots that share a supply path
now fail together, which the depot-level model cannot capture.

Run:  python outage_sim.py

What it does
  1. Calibrate a per-line failure rate so the feeder reproduces SCE's SAIFI.
  2. Simulate many years of line failures/repairs (event-based, continuous time).
  3. For every stretch of time with lines down, find the buses cut off from the
     substation (graph search from bus 0) and record which depots are out.
  4. Report: validation against SAIFI/SAIDI, per-depot outage frequency and
     hours, how often several depots are out together, and sample events.
  5. hourly_states(): the function the 24-step simulation will call. It returns,
     for each hour, which lines are down and which buses/depots are out.

ASSUMPTIONS (state these in any writeup)
  - Every line has the same failure rate; repair time is exponential with mean
    CAIDI. (Real rates differ by line length, overhead vs. underground, exposure.)
  - All SAIFI is attributed to feeder lines; substation and upstream
    (sub-transmission) outages are not modeled separately yet.
  - Customers are weighted by load (kW) when calibrating, because the test
    feeder has no customer counts.
  - No tie-switch restoration: a dropped bus stays out until its line is
    repaired. (feeder_study.py handles switching; combine later.)
  - Unplanned outages only (MED excluded). MED / planned / PSPS are added the
    same way with their own rates, or as hazard scenarios.
"""

from collections import defaultdict, deque

import numpy as np
import pandas as pd
import pandapower.networks as pn

from feeder_study import DEPOT_BUSES

HOURS_PER_YEAR = 8760.0
SAIFI = 0.9037        # interruptions / customer-yr, unplanned, MED excluded (SCE 10-yr avg)
CAIDI_MIN = 107.321   # minutes


# ---------------- feeder topology ----------------
def feeder_graph():
    """In-service lines as (line_idx, from_bus, to_bus), plus load per bus (MW)."""
    net = pn.case33bw()
    ln = net.line[net.line.in_service]
    lines = [(int(i), int(r.from_bus), int(r.to_bus)) for i, r in ln.iterrows()]
    load = net.load.groupby("bus").p_mw.sum().to_dict()
    buses = list(net.bus.index)
    return lines, load, buses


def supplied_buses(lines, failed):
    """Buses reachable from the substation (bus 0) when `failed` lines are out."""
    adj = defaultdict(list)
    for i, a, b in lines:
        if i not in failed:
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


# ---------------- calibration ----------------
def calibrate_line_rate(lines, load, buses):
    """
    On a radial feeder, a failure of line l interrupts every customer downstream.
    So SAIFI = sum_l lambda_l * (share of customers downstream of l).
    With one common rate: lambda_line = SAIFI / sum_l share_l.
    """
    total = sum(load.values())
    all_b = set(buses)
    shares = {}
    for i, _, _ in lines:
        lost = all_b - supplied_buses(lines, {i})
        shares[i] = sum(load.get(b, 0.0) for b in lost) / total
    lam_line = SAIFI / sum(shares.values())
    return lam_line, shares


# ---------------- event generation ----------------
def down_intervals(lam_per_h, mttr_h, horizon_h, rng):
    """
    Alternating renewal process for one component over [0, horizon_h].
    Starts in steady state (down with probability U). Returns list of (start, end).
    """
    U = lam_per_h / (lam_per_h + 1.0 / mttr_h)
    t, out = 0.0, []
    if rng.random() < U:                      # already down at t=0
        d = rng.exponential(mttr_h)           # memoryless: remaining time ~ Exp
        out.append((0.0, min(d, horizon_h)))
        t = d
    while t < horizon_h:
        t += rng.exponential(1.0 / lam_per_h)  # up time
        if t >= horizon_h:
            break
        d = rng.exponential(mttr_h)            # down time
        out.append((t, min(t + d, horizon_h)))
        t += d
    return out


def simulate(years=20_000, seed=1):
    """Event-based simulation; returns per-bus stats, depot co-outage stats, sample events."""
    rng = np.random.default_rng(seed)
    lines, load, buses = feeder_graph()
    lam_yr, _ = calibrate_line_rate(lines, load, buses)
    lam_h, mttr_h = lam_yr / HOURS_PER_YEAR, CAIDI_MIN / 60.0
    T = years * HOURS_PER_YEAR

    # change points: +1 when a line goes down, -1 when it is repaired
    events = []
    for i, _, _ in lines:
        for s, e in down_intervals(lam_h, mttr_h, T, rng):
            events.append((s, +1, i))
            events.append((e, -1, i))
    events.sort()

    all_b = set(buses)
    cache = {}
    failed = set()
    bus_hours = defaultdict(float)
    bus_interruptions = defaultdict(int)
    depot_k_hours = defaultdict(float)     # hours with exactly k depots out
    prev_out = set()
    samples = []
    t_prev = 0.0

    for t, kind, i in events:
        dt = t - t_prev
        if dt > 0 and failed:
            key = frozenset(failed)
            if key not in cache:
                cache[key] = all_b - supplied_buses(lines, failed)
            out = cache[key]
            for b in out:
                bus_hours[b] += dt
            k = sum(1 for b in DEPOT_BUSES.values() if b in out)
            depot_k_hours[k] += dt
        # apply the change, then count newly interrupted buses
        if kind == +1:
            failed.add(i)
        else:
            failed.discard(i)
        key = frozenset(failed)
        if key not in cache:
            cache[key] = all_b - supplied_buses(lines, failed)
        out = cache[key]
        for b in out - prev_out:
            bus_interruptions[b] += 1
        if kind == +1 and len(samples) < 8:
            depots = [n for n, b in DEPOT_BUSES.items() if b in out]
            samples.append({"year": int(t // HOURS_PER_YEAR),
                            "day": int((t % HOURS_PER_YEAR) // 24),
                            "hour": round(t % 24, 2),
                            "line_failed": i,
                            "lines_down_now": sorted(failed),
                            "buses_out": len(out),
                            "depots_out": ", ".join(depots) or "-"})
        prev_out = out
        t_prev = t

    return dict(lines=lines, load=load, buses=buses, lam_yr=lam_yr, years=years,
                bus_hours=bus_hours, bus_interruptions=bus_interruptions,
                depot_k_hours=depot_k_hours, samples=samples)


# ---------------- for the 24-step simulation ----------------
def hourly_states(n_hours=24, seed=None, lam_yr=None):
    """
    One sampled trajectory, hour by hour: which lines are down and which
    buses/depots are out. A line counts as down in hour h if it is down for
    any part of [h, h+1). This is what the main simulation consumes.
    """
    rng = np.random.default_rng(seed)
    lines, load, buses = feeder_graph()
    if lam_yr is None:
        lam_yr, _ = calibrate_line_rate(lines, load, buses)
    lam_h, mttr_h = lam_yr / HOURS_PER_YEAR, CAIDI_MIN / 60.0
    down = {h: set() for h in range(n_hours)}
    for i, _, _ in lines:
        for s, e in down_intervals(lam_h, mttr_h, float(n_hours), rng):
            for h in range(int(np.floor(s)), min(int(np.ceil(e)), n_hours)):
                down[h].add(i)
    all_b = set(buses)
    rows = []
    for h in range(n_hours):
        out = all_b - supplied_buses(lines, down[h])
        rows.append({"hour": h,
                     "lines_down": sorted(down[h]),
                     "buses_out": sorted(out),
                     "depots_out": [n for n, b in DEPOT_BUSES.items() if b in out]})
    return pd.DataFrame(rows)


# ---------------- report ----------------
if __name__ == "__main__":
    r = simulate()
    years, load = r["years"], r["load"]
    total = sum(load.values())

    print(f"Calibrated failure rate per line: {r['lam_yr']:.4f} /yr "
          f"(x {len(r['lines'])} lines = {r['lam_yr']*len(r['lines']):.2f} line failures/yr on the feeder)")

    saifi = sum(r["bus_interruptions"][b] * load.get(b, 0) for b in r["buses"]) / total / years
    saidi = sum(r["bus_hours"][b] * load.get(b, 0) for b in r["buses"]) / total / years * 60
    print(f"\nValidation over {years:,} simulated years (load-weighted):")
    print(f"  SAIFI simulated {saifi:.3f}  vs input {SAIFI}")
    print(f"  SAIDI simulated {saidi:.1f} min  vs SAIFI x CAIDI = {SAIFI*CAIDI_MIN:.1f} min")

    rows = []
    for name, b in DEPOT_BUSES.items():
        rows.append({"depot": name, "bus": b,
                     "outages_per_yr": round(r["bus_interruptions"][b] / years, 3),
                     "hours_out_per_yr": round(r["bus_hours"][b] / years, 2)})
    print("\nPer-depot exposure (no tie switching):")
    print(pd.DataFrame(rows).to_string(index=False))

    out_hours = sum(h for k, h in r["depot_k_hours"].items() if k >= 1)
    print("\nWhen at least one depot is out, how many are out together:")
    for k in sorted(r["depot_k_hours"]):
        if k >= 1:
            print(f"  {k} depot(s): {r['depot_k_hours'][k] / out_hours:6.1%} of depot-outage time")

    print("\nFirst few simulated failures:")
    print(pd.DataFrame(r["samples"]).to_string(index=False))

    print("\nExample hourly_states() output (one random day; usually nothing fails):")
    day = hourly_states(seed=7)
    print(day.head(3).to_string(index=False))
    print(f"  ... hours with any line down: {(day.lines_down.str.len() > 0).sum()} of 24")
