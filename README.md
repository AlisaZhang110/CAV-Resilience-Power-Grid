# Project #4 - Grid Layer Starter Code

| File | What it answers | Kind of analysis |
|---|---|---|
| `markov_outages.py` | *When* does a depot's power supply fail, and for how long? | Converts SCE reliability indices into failure/repair probabilities; validates with a random simulation |
| `feeder_study.py` | *What does a failure mean* for each depot's charging power? | Deterministic AC power flow on a test distribution feeder: hosting capacity + single-outage (N-1) checks |

---

## Contents
1. [Setup and running](#setup-and-running)
2. [markov_outages.py](#markov_outagespy)
3. [feeder_study.py](#feeder_studypy)
4. [Assumptions and limitations](#assumptions-and-limitations)
5. [How these fit into the main simulation](#how-these-fit-into-the-main-simulation)
6. [Next steps](#next-steps)
7. [References](#references)

---

## Setup and running

```bash
pip install pandapower numpy pandas      # Python 3.9+
python markov_outages.py                 # prints conversion table + discretization check
python feeder_study.py                   # prints results; writes hosting_capacity.csv and n_minus_1.csv
```

Works in VS Code, Jupyter, or Google Colab (`!pip install pandapower`). pandapower may warn that `numba` is missing; that only affects speed and can be ignored (or `pip install numba`).

---

## markov_outages.py

### Purpose
Replace the fixed grid-availability parameter α_v with a depot whose power supply switches between **UP** and **DOWN** over time, using the SCE reliability indices already in the Failure Mode Table.

### Inputs
`OUTAGE_CLASSES` holds (SAIFI per year, CAIDI in minutes) for three outage classes, copied from the Failure Mode Table (SCE 2025 Annual Electric Reliability Report, 10-year averages 2016–2025 for unplanned; derived values for MED and planned — see the table's Working sheet):

| Class | SAIFI (/yr) | CAIDI (min) |
|---|---|---|
| Unplanned, MED excluded | 0.9037 | 107.321 |
| Major event day | 0.1834 | 516.914 |
| Planned maintenance | 0.3113 | 300.183 |

### Functions

**`markov_params(saifi, caidi_min, dt_h=1.0)`** — converts indices to model parameters:

| Quantity | Formula | Meaning |
|---|---|---|
| λ (failure rate) | SAIFI / 8760 | failures per hour |
| μ (repair rate) | 1 / (CAIDI in hours) | repairs per hour |
| p_fail | 1 − e^(−λΔt) | P(UP → DOWN) in one timestep |
| p_repair | 1 − e^(−μΔt) | P(DOWN → UP) in one timestep |
| U (unavailability) | λ / (λ + μ) | long-run fraction of time DOWN |

**`simulate_continuous(saifi, caidi_min, years=200_000)`** — validation only. Alternates exponentially distributed up-times (mean 1/λ) and down-times (mean CAIDI) for 200,000 simulated years and returns average downtime in minutes per year.

**`__main__`** — prints the conversion table and a discretization check.

### Principles used
- **Poisson process / exponential distribution.** Failures arrive randomly at a constant average rate; the time between them is exponential. The exponential is *memoryless*: the chance of failing in the next hour doesn't depend on how long the depot has been up.
- **Rate → probability.** For a Poisson process, P(at least one event in Δt) = 1 − e^(−rate·Δt). For tiny rates this ≈ rate·Δt; for large rates (repair) it does not (μ = 0.56/h but p_repair = 0.43).
- **Two-state continuous-time Markov chain.** Steady-state unavailability is λ/(λ+μ).
- **Consistency identity.** CAIDI is defined as SAIDI/SAIFI, so the model must reproduce SAIDI ≈ SAIFI × CAIDI.
- **Inverse-CDF sampling.** `rng.exponential` transforms a Uniform[0,1] draw U into −ln(1−U)/rate.
- **Law of large numbers.** Over enough simulated years, simulated downtime converges to the analytic value.
- **Geometric distribution (discretization).** With 1-hour steps, the number of hours a depot stays down is geometric with mean 1/p_repair, which overstates the true mean outage length.

### Results

| Class | P(fail)/h | P(repair)/h | P(any outage in 24 h) | Analytic downtime (min/yr) | SAIFI×CAIDI | Simulated |
|---|---|---|---|---|---|---|
| Unplanned | 1.03×10⁻⁴ | 0.428 | 0.25% | 97.0 | 97.0 | 96.9 |
| Major event day | 2.09×10⁻⁵ | 0.110 | 0.05% | 94.8 | 94.8 | 95.1 |
| Planned | 3.55×10⁻⁵ | 0.181 | 0.09% | 93.4 | 93.4 | 93.7 |

Discretization bias at Δt = 1 h: mean outage 1.79 h → 2.34 h (unplanned), 8.62 → 9.12 h (MED), 5.00 → 5.52 h (planned).

### What the results mean
- The model reproduces the source data (unplanned: 97.0 min/yr analytic vs. 97.2 min/yr SAIDI in the table).
- **Routine outages are rare on any single day (≈0.25%).** A Monte Carlo that samples ordinary days will almost never see a grid failure. The main simulation needs **hazard-conditioned sampling**: simulate each hazard scenario given that it occurs, then weight by its annual rate.
- The three classes contribute similar annual downtime (~95 min each): rare, long outages matter as much as frequent, short ones.

---

## feeder_study.py

### Purpose
Turn "grid availability" into a computed quantity. Your notes distinguish three grid quantities for a depot: (1) connection state, (2) rated capacity, (3) deliverable capacity under stress. This script computes (1) via network topology and (3) via power flow, on a standard test feeder with candidate depots attached as loads.

### The test feeder
`pandapower.networks.case33bw()` — the Baran & Wu (1989) 33-bus distribution feeder:
- 33 buses at 12.66 kV, base load 3.715 MW / 2.3 MVAr
- 32 normally closed lines forming a **radial tree** from the substation (bus 0)
- 5 normally open **tie lines** (20–7, 8–14, 11–21, 17–32, 24–28) available for restoration
- **No line ratings** are included in the case (all set to a placeholder 99,999 kA)

> Bus numbering: the code uses pandapower's 0-based indices. Papers number buses from 1, so code bus 17 = "bus 18" in the literature.

### Parameters (top of file)

| Parameter | Value | Source |
|---|---|---|
| `V_MIN`, `V_MAX` | 0.95 / 1.05 p.u. | ±5%, consistent with ANSI C84.1 Range A |
| `SUB_V` | 1.05 p.u. | **Assumption** — substation tap changer regulating high. At the default 1.00 p.u. the unmodified feeder already sags to 0.913 p.u. |
| `LOADING_MAX` | 100% | Line current ≤ rating |
| `TRUNK_RATING_KA` / `OTHER_RATING_KA` | 0.30 / 0.15 kA | **Invented placeholders** (case has no ratings) |
| `DEPOT_BUSES` | 5, 17, 21, 32 | Chosen to be electrically different: mid-trunk, end of main feeder, short lateral near substation, end of a long lateral |
| `DEPOT_MW_N1` | 0.3 / 0.05 / 0.5 / 0.1 MW | **Chosen** so the all-lines-in (N-0) case passes limits |
| `PF` | 0.95 lagging | **Assumption** — depot power factor |
| `STEP_MW` | 0.1 MW | Hosting-capacity sweep resolution |

### Functions

**`build_net()`** — loads the 33-bus case, attaches placeholder line ratings, sets the substation voltage.

**`add_depot(net, bus, p_mw, name)`** — adds a depot as a constant-power load: real power P plus reactive power Q = P·tan(arccos PF) ≈ 0.33P.

**`check(net)`** — runs AC power flow (`pp.runpp`) and returns the minimum/maximum bus voltage, maximum line loading, pass/fail, and which constraint broke and where. De-energized buses (NaN results) are excluded. Non-convergence counts as failure.

**`base_case()`** — one power flow on the unmodified feeder as a sanity check.

**`hosting_capacity()`** — for each depot bus *alone*: rebuild the network, add a depot, raise its size in 0.1 MW steps until `check` fails. Reports the last passing size and the binding constraint.

**`n_minus_1()`** — single-outage contingency analysis:
1. Build the N-0 case (all depots at `DEPOT_MW_N1`) and confirm it passes.
2. For each of the 32 in-service lines: copy the N-0 network, switch that line off.
3. `topology.unsupplied_buses` searches the network graph outward from the substation; unreachable buses are de-energized.
4. Run power flow on the energized part; record which depots were dropped.
5. Try closing each tie line alone. Skip ties that don't reconnect every bus. Keep the best one (passes limits first, then highest minimum voltage).
6. Tabulate and summarize.

### Principles used
- **Per-unit system.** Voltages as fractions of nominal (0.95 p.u. = 95% of 12.66 kV).
- **AC power flow.** Given each load's P and Q and a fixed substation voltage, solve the nonlinear power-balance equations for every bus voltage (magnitude and angle). pandapower uses **Newton–Raphson** iteration. Non-convergence means no physical operating point exists (voltage collapse).
- **Slack bus.** The substation is an unlimited source with fixed voltage that supplies all load plus losses. The feeder study therefore tests whether the *wires* can deliver power, not whether enough generation exists.
- **Voltage drop.** Across one line, ΔV ≈ (R·P + X·Q)/V. Drops accumulate along the path from the substation, and each line carries all load downstream of it, so far-end buses are weakest.
- **Reactive power.** Q does no useful work but still flows through lines and contributes to voltage drop (the X·Q term).
- **Thermal loading.** Current ÷ rating; sustained overload overheats conductors and transformers.
- **Hosting capacity.** The largest added load before the first limit binds.
- **Radial topology and graph connectivity.** The feeder is a tree. Removing any line disconnects everything downstream: an outage, not an overload. Whether a bus is supplied is a graph-reachability question, the same idea as the road-network layer.
- **Tree property.** Removing one edge splits a tree into two components; adding one edge between them makes a tree again. So restoring with a single tie always leaves a radial network.
- **Contingency (N-1) analysis.** Remove one element at a time and check whether all load can still be served within limits. This is NERC TPL-001 planning event category P1. On a radial system the real question is whether an alternate feed (tie switch) can pick up the dropped load within limits.

### Results

**Base case:** min voltage 0.968 p.u., max line loading 66.4%, load 3.71 MW.

**Hosting capacity (each depot alone):**

| Depot | Bus | Hosting capacity | Binding constraint |
|---|---|---|---|
| Strong lateral | 21 | 2.0 MW | Overload on line 0 (substation exit) |
| Mid-trunk | 5 | 0.9 MW | Undervoltage at bus 17 |
| Weak lateral | 32 | 0.3 MW | Undervoltage at bus 32 |
| Feeder end | 17 | 0.1 MW | Undervoltage at bus 17 |

**N-1 (depots at `DEPOT_MW_N1`):** N-0 passes (min V 0.955, max loading 81.7%). All 32 single-line outages drop load. Closing a single tie restores all load within limits in **14 of 32**. The substation-exit line (0–1) cannot be restored by any tie (single source).

**Selected restoration cases:**

| Outage | Tie closed | Outcome | Why |
|---|---|---|---|
| Line 1–2 (trunk) | 20–7 | Fails: 0.765 p.u.; lines 1–18, 18–19, 19–20 at ~190% (41 A → 293 A on 1–18) | 27 buses rerouted through a thin lateral |
| Line 28–29 | 17–32 | Fails: 0.833 p.u., no line above 85% | Re-fed buses sit at the end of the longest path |
| Line 5–6 | 11–21 | Passes: 0.962 p.u., lateral at 67% | Small transfer over a short path |

### What the results mean
- **Electrical location matters a lot.** Hosting capacity differs ~20× across buses on one feeder. 0.1 MW is less than one 150 kW fast charger; 2.0 MW is roughly a dozen. A depot sited only on road-network centrality could land where the grid can barely serve it.
- **Caveat:** the 2.0 MW figure at bus 21 is set by the *invented* trunk rating. The voltage-limited figures come from the case's real impedances (but depend on the 1.05 p.u. setpoint).
- **Hosting capacity and restorability rank depots differently.** Bus 21 has the best hosting capacity but the worst restorability: no outage on its lateral can be restored within limits by one tie. This supports a multi-dimensional resilience function rather than a single metric.
- **Restoration success depends on transferred load and path length.** Large transfers over long paths produce undervoltage, overload, or both. On a radial feeder the stress appears when load is *re-fed*, not when the line fails. (On meshed transmission, flow redistributes automatically and instantly, which is where classic N-1 thermal overloads come from.)

---

## Assumptions and limitations

| Item | Current treatment | Effect / fix |
|---|---|---|
| Line ratings | Invented (0.30 / 0.15 kA) | Thermal results depend on them. Use typical conductor ampacities or vary them in a sensitivity sweep |
| Substation voltage | 1.05 p.u. | Voltage-limited results shift with it. State it; optionally sweep 1.00–1.05 |
| Road–feeder mapping | Not yet defined | Must be stated explicitly; standard practice in coupled-network papers (no shared geography) |
| SAIFI as a per-depot rate | Approximation | SAIFI is a customer-weighted system average |
| Depot independence | Depot-level Markov treats depots independently | Violated by PSPS, major events, and shared feeder lines. Fix: line-level failures + feeder topology; PSPS footprint model |
| Outage durations | Exponential | Real durations are skewed (Jan 7 2025 MED: 52% of customers restored < 1 h, 2.5% out ≥ 7 days). Consider lognormal (semi-Markov) |
| Time step | 1 h | Inflates short outages (1.79 → 2.34 h). Sample continuous durations and round up |
| Power flow | Single snapshot at base load | No daily load curve; use pandapower time series later |
| Phases | Balanced three-phase | Unbalanced studies need OpenDSS |
| Restoration | One tie, all-or-nothing | Real operators can close several switches or shed part of the load |
| Violation handling | Flagged "not ok" only | Need a rule: binary, curtailment (recommended), or priority shedding |

---

## How these fit into the main simulation

### Roles

| Piece | Question | Output per hour |
|---|---|---|
| Markov model + hazard table | Which grid lines and road edges are out? | Failed-line set, blocked-edge set |
| Feeder function | Given failed lines, how much power can each depot draw? | `deliverable_kW[depot]` |
| Main simulation (to build) | Given depots and roads, how does the fleet perform? | ϕ(t): reachability, charging access, trips completed |

### One simulated day

```
for each Monte Carlo run (one simulated day):
    sample hazard scenario (none, PSPS, major event day, earthquake, ...)
    for hour t in 0..23:
        1. FAILURES  routine: Markov step per line/edge; hazard: scenario footprint + sampled durations
        2. GRID      failed lines -> best tie switch -> power flow -> deliverable_kW per depot
        3. ROADS     remove blocked edges, reduce capacity on congested ones
        4. FLEET     serve trips, drain batteries, charge (limited by deliverable_kW),
                     reroute or queue at weak depots, strand if no depot reachable
        5. RECORD    phi(t) for each performance dimension
    resilience for run = area under phi(t)
weight runs by scenario annual rate -> expected resilience R
repeat for each depot placement, reusing the same random scenarios (common random numbers)
```

### Integration decisions
1. **Depot ↔ bus mapping.** Write an explicit table (depot A ↔ bus 5, ...). This is where grid hosting capacity and road centrality interact.
2. **Grid function + cache.** Refactor the N-1 logic into `deliverable_kw(failed_lines) -> dict[depot, kW]` and memoize on `frozenset(failed_lines)`. The N-1 table only covers single outages; hazards cause multiple. Most hours have nothing out, so most calls hit the cache.
3. **Violation rule.** Use **curtailment**: reduce a depot's load until limits pass (same sweep as `hosting_capacity()`, run in the post-outage configuration). The result is deliverable capacity under stress.
4. **Coupling depth**, in stages:
   - *One-way:* depot load fixed at rated size; grid limits fleet.
   - *Two-way (demand):* depot load = AVs charging × charger kW, so surges (evacuation, stranded vehicles) can push weak feeders into curtailment.
   - *Two-way (repair):* a line's repair is delayed if road edges to it are blocked (crew access). Few published papers model this.

---

## References

**Data**
- SCE 2025 Annual Electric Reliability Report — SAIFI/SAIDI/CAIDI values, via the project Failure Mode Table (Assumptions and Working sheets).

**Test system and tools**
- Baran, M. E., & Wu, F. F. (1989). Network reconfiguration in distribution systems for loss reduction and load balancing. *IEEE Transactions on Power Delivery*, 4(2), 1401–1407.
- pandapower documentation, contingency analysis: https://pandapower.readthedocs.io/en/latest/contingency.html
- OpenDSSDirect.py (unbalanced alternative): https://github.com/dss-extensions/OpenDSSDirect.py
- Transportation network test data (Sioux Falls): https://github.com/bstabler/TransportationNetworks

**Coupled power–transportation hazard modeling**
- Wang et al. (2025). Risk Assessment and Vulnerability Identification of Energy-Transportation Infrastructure Systems to Extreme Weather. arXiv:2501.13473 — closest open codebase to this project.
- Panteli, M., Pickering, C., Wilkinson, S., Dawson, R., & Mancarella, P. (2017). Power system resilience to extreme weather: fragility modeling, probabilistic impact assessment, and adaptation measures. *IEEE Transactions on Power Systems*, 32(5), 3747–3757.
- Zou, Q., & Chen, S. (2020). Resilience modeling of interdependent traffic-electric power system subject to hurricanes. *Journal of Infrastructure Systems*, 26(1), 04019034.
- Resilience of interdependent power and transportation networks under extreme events: a systematic literature review (2026): https://www.sciencedirect.com/science/article/pii/S2590198226004434

**Planning context**
- NPPD Facility Connection Requirements (v7.1, Sept 2025) — sub-transmission at 34.5–69 kV operated as a radial delivery system: https://docs.nppd.com/FacilityConnectionRequirements.pdf
- NERC TPL-001-5.1, Transmission System Planning Performance Requirements (planning events P0–P7).
- PNNL-32460, *Electric Vehicles at Scale* — transformer thermal and voltage violations typically limit EV hosting capacity: https://www.pnnl.gov/main/publications/external/technical_reports/PNNL-32460.pdf
