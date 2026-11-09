# Project #4 — 10-node AV/HV traffic simulation (failure mode #2)

`av_traffic_sim.py` simulates one day of traffic on the 10-node network from the Project #4 notes (page 5 sketch).
It has 100 cars, 5 of which are AVs. The only failure mode included is **failure mode #2** from the Failure Mode
Table: a human-driver traffic incident that fully blocks one edge ("mid" severity, no capacity).

The same day can be run with and without failures. Every car uses its own random-number stream, so both runs give
cars the same sequence of destinations. Any difference between the two runs therefore comes from the blocked edges.

---

## Requirements

- Python 3.9+
- `networkx` (`pip install networkx`)

No other dependencies.

---

## Quick start

```bash
python av_traffic_sim.py                       # one day: baseline vs. random traffic (seed 1)
python av_traffic_sim.py --seed 7              # a different random day
python av_traffic_sim.py --force 5-6@480+60    # block Culver City–Downtown LA at 08:00 for 60 min
python av_traffic_sim.py --sweep               # block each edge in turn, 60 min at 08:00
python av_traffic_sim.py --days 200            # average of 200 independent days
```

### Command-line options

| Option | Default | What it does |
|---|---|---|
| `--seed N` | `1` | Random seed for a single-day run. The same seed always gives the same day. |
| `--force u-v@start+dur` | none | Blocks edge `u–v` (node numbers) starting at minute `start` for `dur` minutes. Can be repeated to add several blocks. **Turns random traffic off**, so only the forced blocks happen. |
| `--sweep` | off | Runs the single-edge test: each of the 17 edges is blocked by itself for 60 min starting at 08:00 (minute 480), with no other failures. |
| `--days N` | `0` (off) | Runs N independent days (seeds `0` to `N-1`) both with and without traffic, then prints the averages. Ignores `--seed`. Takes about 0.5 s per day. |
| `--logs PREFIX` | `run` | File-name prefix for the CSV logs (see below). |

Time is measured in **minutes from the start of the day**: 0 = 00:00, 480 = 08:00, 1439 = 23:59.

---

## What the model does

### Network

The nodes and edges were copied from the hand-drawn graph on page 5 of the notes. Edges are undirected.

| # | Node |
|---|---|
| 1 | Santa Monica |
| 2 | Sawtelle |
| 3 | West Hollywood |
| 4 | LAX |
| 5 | Culver City |
| 6 | Downtown LA |
| 7 | Playa del Rey |
| 8 | Mid-City |
| 9 | Hollywood |
| 10 | Pasadena |

**Every node is a charger.** The notes (page 5) originally had chargers only at {1, 2, 4, 5}. To go back to that,
set `CHARGERS = {1, 2, 4, 5}` near the top of the script.

The sketch shows 17 edges. (The notes text says "18 cases" for edge failure.) The sketch has no distances, so each
edge length is an **assumption**: the straight-line distance between rough neighborhood centers, times 1.3 for road
winding. Travel time assumes 25 mph and is rounded to whole minutes.

| Edge | Between | Miles | Minutes |
|---|---|---|---|
| 1–2 | Santa Monica – Sawtelle | 4.0 | 10 |
| 2–3 | Sawtelle – West Hollywood | 7.6 | 18 |
| 3–9 | West Hollywood – Hollywood | 2.5 | 6 |
| 9–10 | Hollywood – Pasadena | 14.6 | 35 |
| 1–5 | Santa Monica – Culver City | 7.1 | 17 |
| 1–7 | Santa Monica – Playa del Rey | 6.6 | 16 |
| 2–5 | Sawtelle – Culver City | 3.8 | 9 |
| 3–5 | West Hollywood – Culver City | 6.7 | 16 |
| 5–6 | Culver City – Downtown LA | 11.7 | 28 |
| 5–4 | Culver City – LAX | 7.2 | 17 |
| 5–8 | Culver City – Mid-City | 3.6 | 9 |
| 5–7 | Culver City – Playa del Rey | 6.8 | 16 |
| 4–8 | LAX – Mid-City | 9.9 | 24 |
| 8–9 | Mid-City – Hollywood | 5.0 | 12 |
| 8–6 | Mid-City – Downtown LA | 8.3 | 20 |
| 9–6 | Hollywood – Downtown LA | 7.3 | 18 |
| 6–10 | Downtown LA – Pasadena | 11.3 | 27 |

To use real road distances, edit `COORDS` or overwrite the `miles` and `minutes` values in `build_graph()`.

### Cars

- **Start:** 10 cars at each node (100 total). 5 cars, chosen at random, are AVs.
- **Trips:** each car picks a random destination other than where it is (all other nodes equally likely). It drives
  the fastest open route, stops for **60 min**, and then repeats until the day ends.
- **Routing:** at every node, a car recalculates its fastest route using only the edges that are open at that moment.
  Cars don't know how long a blockage will last. If no open route exists, the car waits at the node and tries again
  every minute.
- **Caught on a blocked edge:** a car that is already partway along an edge when it gets blocked stops there until the
  edge reopens.

### AV charging

- Every AV starts with a random range between 60 and 180 mi (assumption). Driving uses 1 mile of range per mile
  traveled. Human-driven cars have no range limit.
- The range check happens **when an AV is about to start a new trip**. If it has less than 50 mi left, it charges
  for 30 min where it is. Every node is a charger, so the AV never needs to drive anywhere to charge.
  - The code still supports chargers at only some nodes. With fewer chargers, an AV that needs to charge somewhere
    without one first drives to the nearest charger it can reach (by current travel time), then charges 30 min.
- Charging adds 1.8 kWh/min × 30 min × 3.5 mi/kWh ≈ 189 mi, capped at 180 mi. In practice, every charge fills the AV.
  (Range and charge figures are the Waymo numbers in the notes.)

### Failure mode #2: one edge blocked

- **How often:** each edge has a 0.002308 chance per hour of being fully blocked. That is column R of row 2 in the
  Failure Mode Table. It is converted to a chance per minute, and every open edge is checked every minute.
- **How long:** each blockage lasts a random time drawn from a normal distribution, mean 60 min and standard deviation
  20 min (the 20 is an assumption). Results are cut off to stay between 30 and 120 min, matching row 2's "0.5–2 h"
  duration.
- **Scope:** a blocked edge is closed in **both directions**.
- **Expected count:** 17 edges × 24 h × 0.002308 ≈ **0.94 blockages per day**. About 39% of single days have no
  blockage at all, so use `--days` or `--force` to see an effect.

> **Rate caveat:** the per-edge rate in column R assumes 15 edges, 9 of them freeways (Assumptions sheet). Applying it
> to all 17 drawn edges makes the network-wide rate about 1.9× the table's 0.0208 per hour. The rate can be changed in
> `Params.p_block_per_edge_per_hour`.

---

## Outputs

### 1. Printed summary (every mode except `--sweep` and `--days`)

The printout shows the day without traffic (**BASELINE**), then the same day with traffic (**STOCHASTIC TRAFFIC** or
**FORCED BLOCK**). Next it lists each edge blockage and each AV charging event.

Example (`--seed 2`):

```
BASELINE (no traffic), seed 2
  completed_trips                  1621
  av_trips                         79
  mean_trip_min                    29.47
  total_delay_min                  0
  ...
STOCHASTIC TRAFFIC (failure mode #2), seed 2
  completed_trips                  1618
  av_trips                         79
  mean_trip_min                    29.61
  total_delay_min                  186
  trips_delayed_gt_1min            3
  trips_rerouted                   5
  minutes_stuck_on_blocked_edges   174.0
  edge_block_events                1
  av_charge_events                 7
  av_stranded                      0

Edge blockages:
   {'edge': 'Downtown LA - Mid-City', 'start_min': 1287, 'duration_min': 86.8, 'forced': False}
```

| Metric | Meaning |
|---|---|
| `completed_trips` | Trips finished before the day ends. Counts only random-destination trips; drives to a charger are not included. |
| `av_trips` | How many of those trips were made by AVs. |
| `mean_trip_min` | Average trip time, door to door, in minutes. |
| `total_delay_min` | Total minutes by which trips took longer than they would on an empty network. |
| `trips_delayed_gt_1min` | Number of trips delayed by more than 1 minute. |
| `trips_rerouted` | Trips that ended up on a different route from the empty-network fastest route. |
| `minutes_stuck_on_blocked_edges` | Car-minutes spent stopped on an edge after it was blocked. |
| `edge_block_events` | Number of blockages that started during the day. |
| `av_charge_events` | Number of AV charging sessions. |
| `av_stranded` | Times an AV's range hit 0 or below (see Known limitations). |

### 2. `--sweep` table

```
  edge                                trips  delay_min  rerouted  stuck_min
  Santa Monica - Sawtelle              1612      107.0         9         60
  ...
```

Each row is a separate day with only that edge blocked (60 min starting at 08:00).

- `trips`: completed trips that day.
- `delay_min`: extra delay compared with the no-traffic day.
- `rerouted` and `stuck_min`: same meaning as in the summary table above.

Each row is a single day (same seed), so expect noise. Use the table to compare edges, not as exact values.

### 3. `--days N` table

For each metric, this table gives the average across N days, without traffic and with traffic.

### 4. CSV logs (single-day and `--force` runs only)

The logs come from the traffic run, not the baseline. They are saved in the current folder. A log is skipped if it
would be empty; for example, `run_blocks.csv` is missing on a day with no blockages.

**`<prefix>_trips.csv`**: one row per completed trip, including drives to a charger.

| Column | Meaning |
|---|---|
| `car` | Car ID (0–99; IDs 0–9 start at node 1, 10–19 at node 2, …) |
| `av` | `True` if the car is an AV |
| `purpose` | `trip` (random destination) or `to_charger` (only appears when some nodes have no charger) |
| `origin`, `dest` | Node names |
| `start_min`, `end_min` | Departure and arrival time (minutes from 00:00) |
| `actual_min` | Trip time |
| `freeflow_min` | Fastest possible time on the empty network |
| `delay_min` | `actual_min − freeflow_min` |
| `reroutes` | Number of times the route changed during the trip |
| `stuck_on_blocked_edge_min` | Minutes stopped on a blocked edge |
| `waited_no_route_min` | Minutes spent waiting at a node because no open route existed |

**`<prefix>_blocks.csv`**: `edge`, `start_min`, `duration_min`, `forced`

**`<prefix>_charges.csv`**: `car`, `node`, `start_min`, `range_before` (mi), `range_after` (mi)

---

## Changing parameters

All model settings are in the `Params` class near the top of the script. Each one is tagged with where it came from:

- `[DOC]`: taken from the notes or the Failure Mode Table
- `[USER]`: from the task spec
- `[ASSUMPTION]`: chosen for this prototype

| Parameter | Value | Source |
|---|---|---|
| `sim_minutes` | 1440 | [DOC] 24 h day |
| `n_cars`, `n_av`, `cars_per_node` | 100, 5, 10 | [USER] |
| `dwell_min` | 60 | [USER] |
| `av_charge_threshold_mi`, `av_charge_min` | 50, 30 | [USER] |
| `av_max_range_mi` | 180 | [DOC] Waymo 120–180 mi |
| `charge_kwh_per_min`, `mi_per_kwh` | 1.8, 3.5 | [DOC] Waymo breakdown |
| `av_start_range_mi` | 60–180 | [ASSUMPTION] |
| `p_block_per_edge_per_hour` | 0.002308 | [DOC] Failure table row 2, col R |
| `block_mean_min` | 60 | [USER] / [DOC] "central ~1 h" |
| `block_sd_min` | 20 | [ASSUMPTION] |
| `block_min_min`, `block_max_min` | 30, 120 | [DOC] "0.5–2 h" |
| `CIRCUITY`, `AVG_SPEED_MPH` | 1.3, 25 | [ASSUMPTION] |

---

## Known limitations

- **Running out of charge.** With every node a charger, no AV ran out in 200 simulated days. Each trip starts with at
  least 50 mi of range, and the longest possible trip is about 30 mi (about 35 mi if one edge is blocked). With
  chargers only at {1, 2, 4, 5}, AVs ran out on about 5% of days. That's because the 50-mile check only happens when
  a trip starts: an AV at 51 mi can take a long trip and then not have enough range left to reach a charger.
- **No congestion.** Cars do not slow each other down, and edges have no capacity limit. A blockage only matters to
  cars that need that edge.
- **Chargers have no capacity.** Any number of AVs can charge at the same station at once, and the grid is always
  available.
- **Same blockage chance everywhere.** Every edge uses the same rate. The table's freeway vs. arterial split is not
  applied yet.
- **No real trip patterns.** Destinations are uniformly random. The gravity model in the notes is not used yet.
- **No time-of-day effects.** Trip demand and blockage risk are the same at every hour.
- **One failure mode only.** Failure modes 1, 1b, 3–18 are not included.
