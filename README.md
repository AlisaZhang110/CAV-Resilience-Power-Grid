# CAV Charging-Depot Resilience — Coupled Power–Transportation Simulation

GIRS Project #4. A 10-node prototype of LA's Westside–Downtown–Pasadena corridor. Autonomous ride-hail vehicles (AVs)
share the road network with human drivers and charge at depots fed by a distribution grid. Hazards from the Failure
Mode Table close roads, cut road capacity, and black out depots. The goal is to compare depot placements by how well
the fleet keeps serving trips through those hazards.

```
                      HAZARD LAYER  (data/Failure_Mode_Table.xlsx)
              rates, durations, footprints per row (traffic, weather, power, fire, flood, quake)
                 |                                              |
       road closures / capacity cuts               failed lines / dark depots
                 v                                              v
   TRAFFIC LAYER  (traffic/)                         GRID LAYER  (grid/)
   10-node road graph, hourly human + AV demand,     IEEE 33-bus feeder, line-level Markov outages,
   congestion, AV dispatch + charging                switching, power flow, deliverable MW per depot
                 \______________ depot <-> bus mapping (to build) ______________/
```

## Repository layout

| Path | What it is | Status |
|---|---|---|
| `data/Failure_Mode_Table.xlsx` | Hazard rates, durations, sources, priority and feasibility rankings | Complete |
| `traffic/v3_time_of_day/` | **Current traffic layer.** Hourly human/AV demand (NHTS 2017), BPR congestion, AV fleet dispatch and charging, table rows 1, 1b, 1c, 2, 4, 5, 9, 10 (+ forced 11, 12) | Runs; see its README |
| `traffic/v3_time_of_day/analysis/` | Scripts, saved results and figures behind the Nov 2026 advisor slides | Reproducible; see its README |
| `traffic/v2_failure_mode_2/` | Earlier version: 100 looping cars, row 2 only. Kept for comparison | Superseded |
| `grid/` | **Current grid layer** (`grid_layer` package + `run_examples.py`): routine outages calibrated to SCE SAIFI/CAIDI, PSPS / earthquake / storm scenarios, restoration switching, curtailment | Runs; see its README |
| `grid/legacy/` | First grid scripts (`markov_outages.py`, `feeder_study.py`, `outage_sim.py`) and their README | Superseded by `grid/grid_layer` |

## Quick start

```bash
pip install -r requirements.txt

cd traffic/v3_time_of_day
python av_traffic_sim_tod.py                       # one weekday: congestion-only baseline vs. stochastic hazards
python av_traffic_sim_tod.py --sweep --sweep-start 1020   # which single edge hurts most at 17:00
python av_traffic_sim_tod.py --days 100            # 100-day averages

cd ../../grid
python run_examples.py                             # calibration, N-1, ordinary week, PSPS, earthquake, storm
```

## Failure Mode Table coverage

| Row | Hazard | Where |
|---|---|---|
| 1, 4 | Human / AV incident, reduced capacity | traffic v3 (stochastic) |
| 1b | Rain day | traffic v3 (`--rain`) |
| 1c | Recurring congestion | traffic v3 (BPR + hourly demand) |
| 2, 5 | Human / AV incident, edge closed | traffic v3 (stochastic, freeway edges) |
| 3, 6 | Major incident, ≥ 3 edges | not yet |
| 7, 7b, 8 | AV connectivity stall, battery depletion, emergency-response obstruction | 7b appears as an output (stranded AVs); 7 and 8 not yet |
| 9, 10 | Depot power outage, unplanned / major event day | traffic v3 (per-depot), grid (line-level, correlated) |
| 11, 12 | Planned outage, PSPS | traffic v3 (`--outage`), grid (`psps()` scenario) |
| 13–16 | Wildfire / flood edge closures | not yet (needs wildfire-zone and floodplain edge tags + multi-day horizon) |
| 18 | Earthquake | grid (`substation_loss()`); road side not yet |

## Next steps: full depot siting

Planned study (not built yet). It replaces the notes' fixed charger set {1, 2, 4, 5} with an open siting question, and
keeps the notes' set as the benchmark. A first check (`traffic/v3_time_of_day/analysis/siting_check.py`: all 210
four-depot layouts, normal weekdays, uniform demand) already ranks the notes' set #200 of 210 on AV wait.

1. **Gravity demand:** q_ij = K·P_i·A_j / d_ij, with P = resident workers and A = jobs per node (LEHD LODES).
2. **Grid coupling:** map each node to a feeder bus (tied to the grid layer's WUI and floodplain zones), so the power
   each depot can actually draw, hour by hour, sets how many chargers it can run.
3. **Multi-day hazard scenarios** from the Failure Mode Table (major storm, PSPS, wildfire, flood, earthquake), each
   with its annual rate, including correlated multi-depot outages and the road-side closures (rows 3/6, 13–16, 18).
4. **Enumerate every layout of 2–6 depots** (837 layouts) and rank them on normal-day service and on rate-weighted
   expected service lost under the hazard scenarios. Report the trade-off (Pareto) front for each depot count, and
   where the notes' layout falls on it.

## Data sources

- Failure Mode Table: sources listed on its *Sources* sheet.
- Hourly demand profiles: 2017 National Household Travel Survey (FHWA), public trip file. See
  `traffic/v3_time_of_day/build_profiles.py`.
- Grid: Baran & Wu (1989) 33-bus test feeder via pandapower; SCE 2025 Annual Electric Reliability Report.
