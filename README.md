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
                 \_____ depot/signal <-> bus table, coupled every minute (coupled/) _____/
```

**Current headline (coupled/README.md):** with Waymo's existing depots at Santa Monica, Sawtelle, LAX and Culver City,
the best 5th depot is **Downtown LA** (-0.51 min annual rider wait, -6.6%). Hollywood ties it on average, but Downtown
keeps working in a PSPS and has the stronger grid connection. If Tesla adds a fleet, **universal (shared) depots beat exclusive ones** at every
fleet size tested.

## Repository layout

| Path | What it is | Status |
|---|---|---|
| `data/Failure_Mode_Table.xlsx` | Hazard rates, durations, sources, priority and feasibility rankings | Complete |
| `coupled/` | **Coupled simulation.** Grid layer sets each depot's deliverable MW (dark / partial / full) and each node's traffic signals every minute; every Failure Mode Table row; several fleets with universal or exclusive depots; placement and multi-fleet experiments, figures | Runs; see its README |
| `traffic/v3_time_of_day/` | **Current traffic layer.** Hourly human/AV demand (NHTS 2017), BPR congestion, AV fleet dispatch and charging, table rows 1, 1b, 1c, 2, 4, 5, 9, 10 (+ forced 11, 12) | Runs; see its README |
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

cd ..                                              # repo root: coupled simulation
PYTHONPATH=. python -m coupled.experiments all     # ~3,000 simulated days
PYTHONPATH=. python -m coupled.report              # results/ and figures/ under coupled/
```

## Failure Mode Table coverage

Every row is now modeled in `coupled/` (details: `coupled/README.md`, section 2).

| Row | Hazard | Where |
|---|---|---|
| 1, 4 | Human / AV incident, reduced capacity | traffic v3, sampled every minute |
| 1b | Rain day | scenario (34.1 days/yr) |
| 1c | Recurring congestion | BPR + hourly demand |
| 2, 5 | Human / AV incident, edge closed | traffic v3, sampled every minute |
| 3, 6 | Major incident, >= 3 edges | coupled: 1 edge closed + 2 adjacent diversion edges |
| 7 | AV connectivity stall | coupled: scheduled, and triggered when >= 3 nodes have dark signals |
| 7b | Battery depletion | coupled: a stranded AV blocks a lane until towed |
| 8 | AV obstructs incident clearance | coupled: +5/15/30 min, calibrated to 0.17 per AV-year |
| 9, 10, 11 | Unplanned, major-event-day, planned outages | grid layer (line level, switching, curtailment), coupled to depots and signals |
| 12 | PSPS | grid WUI zone (Santa Monica, Hollywood, Pasadena); q = 0.10 is a placeholder |
| 13, 14 | Wildfire, 1 or >= 3 edges | WUI edges closed; row 14 also de-energizes the WUI zone |
| 15, 16 | Flood, 100-yr / 500-yr | Ballona edges closed + floodplain buses dark |
| 18 | Earthquake | freeway edges closed, inspection slowdowns, substation loss |

## Next steps

1. Replace the placeholder node <-> bus table with real feeder/substation assignments (SCE circuit maps), and look
   up PSPS q for each node on SCE's PSPS circuit map.
2. Two-way coupling (fleet demand changes feeder voltages) once depots are sized above ~0.4 MW, where fig 10 shows
   curtailment binding even with nothing failed.
3. Multi-day runs for wildfire / earthquake closures, and weekend days once a weekend ride-hail total is sourced.
4. Several depots per entrant (the exclusive case currently allows Tesla one depot).
5. Gravity-model origins/destinations instead of uniform.

## Data sources

- Failure Mode Table: sources listed on its *Sources* sheet.
- Hourly demand profiles: 2017 National Household Travel Survey (FHWA), public trip file. See
  `traffic/v3_time_of_day/build_profiles.py`.
- Grid: Baran & Wu (1989) 33-bus test feeder via pandapower; SCE 2025 Annual Electric Reliability Report.
- Coupled-model outside sources (dark-signal capacity, Dec 2025 SF outage, ride-hail checks): `coupled/README.md`.
