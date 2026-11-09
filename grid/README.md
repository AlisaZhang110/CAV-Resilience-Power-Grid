# Grid Layer — AV Fleet Resilience Simulation (GIRS Project #4)

The electric-grid building block for the depot-siting resilience simulation. It simulates the grid **day by day, hour by hour**. Each hour it answers three questions:

1. Which buses have power?
2. Did switching restore any of them?
3. How many MW can each charging depot actually draw?

It's built to plug into a transportation layer (the AV fleet on the road graph) and a hazard layer (your Failure Mode Table).

**Status:** runs end to end and is validated against SCE's SAIFI and SAIDI. The full multi-layer simulation and the Monte Carlo over hazard scenarios haven't been built yet; this is the grid piece they'll call.

---

## Contents
1. [Should the whole simulation be in Python?](#1-should-the-whole-simulation-be-in-python)
2. [Where the grid layer fits](#2-where-the-grid-layer-fits)
3. [Quick start](#3-quick-start)
4. [The modules, one by one](#4-the-modules-one-by-one)
5. [Outputs](#5-outputs)
6. [Example results](#6-example-results)
7. [Connecting the transportation layer](#7-connecting-the-transportation-layer)
8. [Connecting the hazard layer](#8-connecting-the-hazard-layer)
9. [Modeling rules and assumptions](#9-modeling-rules-and-assumptions)
10. [What replaced the old scripts](#10-what-replaced-the-old-scripts)
11. [Next steps](#11-next-steps)

---

## 1. Should the whole simulation be in Python?

**Yes.** Your study plan already specifies Python (NetworkX for the graph, NumPy for sampling), and every layer has a mature Python tool:

| Layer | Tool | Why |
|---|---|---|
| Grid | `pandapower` (this package) | AC power flow, topology, contingency studies |
| Road network | `networkx` | Shortest paths, reachability, edge removal; ideal for a 10–25 node stylized graph |
| Fleet / AVs | plain Python classes (agent-style) | Battery, trips, queuing at depots; simple at this scale |
| Hazards / sampling | `numpy` (and `scipy.stats` for LHS) | Inverse-CDF sampling, Monte Carlo |
| Analysis / figures | `pandas`, `matplotlib` | Tables and plots |

Dedicated traffic simulators (SUMO, MATSim) or co-simulation frameworks (HELICS, Mosaik) exist, but they're built for city-scale networks with thousands of vehicles. For a 10-node proof of concept they add setup cost and no research value. Stay in Python, and keep each layer behind a small interface (like `GridLayer.step()`) so one layer could be swapped for a heavier tool later without rewriting the rest.

---

## 2. Where the grid layer fits

The full simulation is a set of layers sharing one clock (hour *t*):

```
                 +-------------------+
                 |   HAZARD LAYER    |  Failure Mode Table: which events happen,
                 | (scenario sampler)|  when, how long, where
                 +---------+---------+
          HazardEvent(s)   |                    road edge closures / capacity cuts
            (lines, buses, |                    +-------------------------------+
             substation)   v                    |                               v
+--------------------------------------+   +--------------------------------------+
|             GRID LAYER               |   |        TRANSPORTATION LAYER          |
|  routine outages + hazard outages    |   |  road graph (networkx) + AV fleet    |
|  -> topology -> switching -> power   |   |  trips, battery, routing, charging   |
|     flow -> curtailment              |   |                                      |
|                                      |   |                                      |
|  step(t, depot_demand) -> HourState  |<--|  depot_demand  (MW wanted per depot) |
|      state.depot_mw  -------------------->|  charging capacity per depot         |
+--------------------------------------+   +-------------------+------------------+
                                                               |
                                                               v
                                                 performance phi(t): reachability,
                                                 charging access, trips completed
                                                 -> resilience = area under phi(t)
```

**The grid layer's job:** turn "what failed" into "how much charging power each depot has" every hour. It knows nothing about vehicles or roads. It only exchanges two dictionaries with the transportation layer: depot demand in, depot capacity out.

---

## 3. Quick start

```bash
pip install pandapower numpy pandas      # Python 3.9+ ; optional: pip install numba (faster)
python run_examples.py                   # runs every scenario, writes CSVs to ./outputs/
```

Minimal use:

```python
from grid_layer import GridLayer, psps

grid = GridLayer(seed=1)
run = grid.simulate(n_days=2, hazards=[psps(start_h=10, duration_h=30)])

run.periods()        # compact: one row per outage period
run.bus_table()      # every bus, every hour: energized? voltage?
run.depot_table()    # every depot, every hour: energized? MW available?
```

The files must stay together: `run_examples.py` next to the `grid_layer/` folder. Run commands from that folder.

---

## 4. The modules, one by one

```
grid_sim/
├── run_examples.py        <- scenarios showing how to use everything
├── outputs/               <- CSVs written by run_examples.py
└── grid_layer/
    ├── params.py          <- every assumption, in one place
    ├── feeder.py          <- physics: topology, switching, power flow, curtailment
    ├── outages.py         <- routine random line failures (Markov)
    ├── hazards.py         <- correlated events from the hazard layer
    ├── layer.py           <- GridLayer: the hourly clock + output tables
    └── studies.py         <- one-off studies: hosting capacity, N-1, validation
```

How data flows through them each hour:

```
params ──> outages.RoutineOutages.sample() ─┐
                                            ├─> list of Outage events ─> layer.GridLayer.step(t)
hazards.HazardEvent.to_outages() ───────────┘                                   │
                                     which lines / buses / substation are out at hour t
                                                                                v
                                                             feeder.Feeder.solve(...)
                                                     topology -> switching -> power flow
                                                                                v
                                                     HourState (bus status, depot MW)
```

### `params.py` — every assumption
**What:** constants only, no code. Voltage and loading limits, line ratings, substation voltage, depot locations and sizes, routine outage rates (SAIFI/CAIDI), hazard zones.
**Why it matters:** change an assumption here once and every module uses it. Every placeholder is labeled `ASSUMPTION`.
**Fits in:** read by every other module. The `DEPOTS` dictionary has a `road_node` field for each depot. Fill it in once the depot↔bus mapping is decided; it's the link to the transportation layer.

### `feeder.py` — the physics
**What:** the `Feeder` class wraps the IEEE 33-bus test feeder. Its main method, `solve(lines_down, buses_failed, substation_up, depot_demand)`, runs four steps:

1. **Topology.** Breadth-first search from the substation (bus 0) through the closed lines. Unreached buses are dark.
2. **Restoration.** Try closing 0, 1 or 2 tie switches. Accept a configuration only if it (a) stays radial (no loops) and (b) carries all restored *customer* load within limits. Pick the one restoring the most customer load, then fewest switch operations, then highest minimum voltage.
3. **Power flow.** AC power flow (Newton–Raphson, via pandapower) for voltages and line loadings.
4. **Curtailment.** If the depots push the network past a limit, reduce depot load until it fits. Depots brought back by switching are cut first. Depots that never lost power are cut only if that isn't enough. The result is each depot's **deliverable MW**.

**Returns:** a `FeederState` with dark buses (before and after switching), ties closed, voltages, max loading, and per-depot `{energized, demand_mw, deliverable_mw}`.
**Speed:** results are cached by outage situation. Most hours have nothing out, so most calls are instant.
**Also:** `power_flow()` for a single configuration; `line_between(a, b)` to look up a line by its two buses.
**Fits in:** the consequence half of risk. It answers "if this is out, what happens?" It has no randomness and no clock.

### `outages.py` — routine random failures
**What:** each of the 32 feeder lines is a two-state Markov component (up/down).
- `calibrate_line_rate()` sets one failure rate per line so the feeder reproduces SCE's SAIFI. On a radial feeder, SAIFI = Σ λ × (share of customers downstream of each line). Result: **0.124 failures per line per year**, about 4 line failures per year on the feeder.
- Repair time is exponential with mean CAIDI (107 min).
- `RoutineOutages.sample(horizon_h, rng)` returns a list of `Outage(element, index, start_h, end_h, cause)` events over the horizon. It starts in steady state and carries over continuously from one day to the next.

**Fits in:** the likelihood half for ordinary days. Outage classes are switched on and off in `params.ROUTINE_OUTAGE_CLASSES` (unplanned is on; planned is available).

### `hazards.py` — correlated events
**What:** `HazardEvent(name, start_h, duration_h, lines, buses, substation)` is the format the hazard layer hands to the grid layer. Builders:
- `psps(start_h, duration_h, zone="WUI")`: de-energizes every line *and bus* in the zone. Switching can't re-feed power into it.
- `substation_loss(start_h, duration_h, cause="earthquake")`: loss of supply at bus 0. Everything goes dark.
- `zone_event(name, zone, start_h, duration_h, p_fail, rng)`: lines in a zone fail. With `p_fail < 1`, each line fails independently, e.g. from a fragility curve.

**Fits in:** hazard *probabilities* live in the hazard layer. This module only translates an event into grid elements. Zones are placeholders in `params.LINE_ZONES` / `ZONE_BUSES` until feeder lines get real locations.

### `layer.py` — the grid layer with a clock
**What:** `GridLayer` is the object the rest of the simulation talks to.
- `reset(n_days, hazards)`: draw routine outages for the horizon and add hazard events.
- `step(t, depot_demand=None)`: grid state at hour *t*, returned as an `HourState`. An outage counts in hour *t* if it covers any part of that hour.
- `simulate(n_days, hazards, depot_demand_fn=None)`: reset, then step through every hour. Returns a `GridRun`.

`HourState.depot_mw` is the `{depot: MW}` dictionary the transportation layer needs.

`GridRun` table views:
- `summary()`: one row per hour.
- `periods()`: consecutive identical hours collapsed into one row.
- `bus_table()`: every bus, every hour.
- `depot_table()`: every depot, every hour.
- `outage_log()`: the raw outage events.

**Fits in:** the interface. The transportation layer and the Monte Carlo driver only ever touch this.

### `studies.py` — one-off studies
- `hosting_capacity()`: largest test load at each bus before a limit binds (nothing failed, no depots).
- `n_minus_1()`: every single-line outage, showing what goes dark, what switching restores, and the deliverable MW per depot.
- `validate_routine(years)`: simulates thousands of years of routine outages and checks SAIFI and SAIDI against the inputs.

**Fits in:** for understanding the feeder, the siting analysis, and validation. Not part of the hourly loop.

---

## 5. Outputs

`run_examples.py` writes to `./outputs/` and prints the full path at the end.

| File | One row per | Columns |
|---|---|---|
| `<scenario>_bus_states.csv` | bus × hour | `day, hour, bus, energized, restored_by_switching, vm_pu, depot` |
| `<scenario>_depot_states.csv` | depot × hour | `day, hour, depot, bus, road_node, energized, demand_mw, deliverable_mw` |
| `<scenario>_summary.csv` | hour | `day, hour, causes, lines_down, substation_up, ties_closed, buses_dark_before, buses_dark, depots_dark, depot_supply_frac, v_min, max_loading_pct` |
| `hosting_capacity.csv` | bus | `bus, hosting_capacity_mw, binding_constraint` |
| `n_minus_1.csv` | failed line | `line, from-to, buses_dark_before, ties_closed, buses_dark_after, depot_supply_frac, v_min, <depot>_mw …` |

`depot_supply_frac` = MW delivered ÷ MW demanded across all depots (1 = fully served). It's a ready-made input for the "charging accessibility" dimension of ϕ.

Bus numbers are 0-based. Papers number buses from 1, so add 1 when citing.

---

## 6. Example results

From `run_examples.py` (seed 1):

**Routine outage model:** 0.124 failures per line per year, 3.98 line failures per year on the feeder, 1.1% chance a random day has any failure. Validation over 5,000 years: SAIFI 0.901 vs. input 0.904; SAIDI 96.8 min vs. 97.0.

**Scenarios:**

| Scenario | Period | What's dark | Depot supply |
|---|---|---|---|
| Ordinary week | 7 days | Nothing (typical: ~7% chance of any failure in a week) | 100% |
| PSPS, WUI zone | 30 h | 8 buses; depots at 21 and 32 | 37% |
| Substation loss (earthquake) | 8 h | Everything | 0% |
| Storm: lines 2–3 and 18–19 | 12 h | 26 buses, all 4 depots; no switching option within limits | 0% |

**N-1 with curtailment:** for 8 single-line outages, switching restores every depot but at reduced power. For example, after line 1–18 fails, tie 20–7 restores the upper lateral; the depot at bus 21 (restored by switching) is cut to 0, and the others run at about 67%. Total depot supply is 32%.

**Coupled loop:** with line 1–18 down, depots get 0.30 MW whether they ask for 0.95 or 1.43 MW. Once the voltage limit binds, extra demand can't be served. That cap is the information the fleet model needs.

---

## 7. Connecting the transportation layer

Each hour, the main loop calls the layers in order:

```python
from grid_layer import GridLayer

grid = GridLayer(seed=run_seed)
grid.reset(n_days=1, hazards=grid_events)            # from the hazard layer
roads.reset(edge_events)                              # same hazards, road side

for t in range(grid.horizon_h):
    demand = fleet.charging_demand(t)                 # {depot: MW} the fleet wants
    g = grid.step(t, depot_demand=demand)             # grid physics for hour t
    roads.step(t)                                     # apply edge closures / congestion
    fleet.step(t, roads.graph, g.depot_mw)            # move, charge (limited by g.depot_mw), reroute
    phi.append(metrics(roads, fleet, g))              # performance this hour
```

What the fleet does with `g.depot_mw[depot]`:
- **0 MW:** the depot is dark. Vehicles reroute to another depot or queue.
- **Below demand:** charging slows. Energy per vehicle per hour = (available MW ÷ vehicles charging) × 1 h.
- **Full:** normal operation.

**Coupling depth** (build in this order):
1. **One-way.** Call `step(t)` with no demand, so every depot draws its rated load. The grid limits the fleet; the fleet doesn't affect the grid.
2. **Two-way, demand.** Pass the fleet's real demand each hour. Surges (evacuation, stranded vehicles) can then push a weak feeder into curtailment, as in scenario 6.
3. **Two-way, repair.** Repairs are delayed when road edges to the damaged line are blocked (crews can't reach it). This goes in the hazard layer: lengthen a `HazardEvent`'s `duration_h` based on road state. Few published papers model this.

The depot↔road link is `params.DEPOTS[...]["road_node"]`. Fill it in, and `depot_table()` carries it through.

---

## 8. Connecting the hazard layer

The hazard layer converts Failure Mode Table rows into `HazardEvent`s (grid side) and edge closures (road side):

| Failure Mode Table row | Grid event |
|---|---|
| Power outage, unplanned | Already covered by routine outages (`outages.py`) |
| Major event day | `zone_event(...)` or a list of lines, ~8.6 h mean |
| PSPS (~5 events/yr touching LA County, 24–48 h) | `psps(start_h, duration_h)` |
| Earthquake M ≥ 6.7 | `substation_loss(...)`, and/or `zone_event(..., p_fail=fragility)` for lines |
| Wildfire | `zone_event("wildfire", "WUI", ..., p_fail=...)` |
| Flood | `zone_event("flood", "floodplain_100yr", ...)` |

**Hazard-conditioned Monte Carlo.** Routine outages hit a random day only ~1% of the time, so sampling ordinary days wastes almost every run. Instead, simulate each scenario given that it happens, then weight by how often it happens:

```python
scenarios = {                       # annual rates from the Failure Mode Table
    "PSPS":       dict(rate=5.0,    make=lambda rng: [psps(rng.uniform(0, 12), rng.uniform(24, 48))]),
    "earthquake": dict(rate=0.0305, make=lambda rng: [substation_loss(rng.uniform(0, 24), 72)]),
    # ...
}
results = {}
for name, sc in scenarios.items():
    vals = []
    for k in range(N_RUNS):
        rng = np.random.default_rng(k)                      # same seeds for every depot layout
        run = GridLayer(seed=k).simulate(n_days=3, hazards=sc["make"](rng))
        vals.append(resilience_metric(run, ...))            # after the fleet layer runs too
    results[name] = np.mean(vals)
# expected annual impact = sum over scenarios of rate x mean impact (plus the routine baseline)
```

Reuse the same seeds for every depot placement you compare (common random numbers), so differences come from the placement, not luck.

---

## 9. Modeling rules and assumptions

| Item | Rule used | Status |
|---|---|---|
| Test feeder | IEEE 33-bus (Baran & Wu, 1989), modified as below | Standard test system |
| Substation voltage | 1.05 p.u. | ASSUMPTION |
| Voltage limits | 0.95–1.05 p.u. | ANSI C84.1 Range A |
| Line ratings | 0.30 kA trunk, 0.15 kA elsewhere | ASSUMPTION (case has none) |
| Depot sizes | 0.30 / 0.05 / 0.50 / 0.10 MW | Chosen so the intact feeder passes |
| Restoration | Up to 2 ties; radial only; only if all restored *customer* load fits within limits; maximize customers restored | Modeling policy |
| Depot priority | Customers first; depots treated as curtailable (flexible interconnection). Depots restored by switching are curtailed before others | Modeling policy |
| Partial restoration | Not modeled: a tie restores its whole dark section or nothing | Simplification (conservative) |
| Routine outages | Equal rate on every line, calibrated to SAIFI (load-weighted); exponential repair, mean CAIDI | Approximation |
| Upstream outages | All of SAIFI attributed to feeder lines; substation loss only via hazards | Simplification |
| Hourly rule | An outage counts in an hour if it covers any part of it | Conservative |
| Hazard zones | `LINE_ZONES` / `ZONE_BUSES` | PLACEHOLDER until geography is mapped |
| Network | One feeder for all depots | Design choice; see next steps |

---

## 10. What replaced the old scripts

| Old | New |
|---|---|
| `markov_outages.py` (depot-level Markov) | `outages.py` (line-level, calibrated to SAIFI). Depot-level is kept only as a benchmark idea |
| `outage_sim.py` (line-level, topology only) | `outages.py` + `layer.py`, now with switching and power flow every hour |
| `feeder_study.py` (hosting capacity, N-1, `study_outage`) | `feeder.py` (`Feeder.solve`) + `studies.py`. N-1 now reports deliverable MW per depot |
| Uniform pass/fail after switching | Customers-first restoration + targeted depot curtailment |

---

## 11. Next steps

1. **Decide the depot↔bus mapping** and fill in `road_node`. Decide whether depots share one feeder or sit on separate feeders (open question for Camila).
2. **Build the transportation layer** (networkx graph + simple fleet) with a `step(t, graph, depot_mw)` method, starting with one-way coupling.
3. **Write the hazard sampler** from the Failure Mode Table: one function per row that returns `HazardEvent`s plus road-edge events.
4. **Monte Carlo driver** with hazard-conditioned sampling, rate weighting, common random numbers, and a convergence check.
5. **Refinements:**
   - real line ratings and a sensitivity sweep on the substation voltage;
   - lognormal outage durations;
   - partial restoration;
   - planned and MED classes;
   - a daily load curve (pandapower time series).

**References:** Baran & Wu (1989), *IEEE Trans. Power Delivery* 4(2):1401–1407 · Billinton & Allan, *Reliability Evaluation of Power Systems* (2nd ed., 1996), two-state Markov model · IEEE Std 1366 (SAIFI/SAIDI/CAIDI definitions) · NERC TPL-001 (N-1 planning events) · pandapower docs: https://pandapower.readthedocs.io
