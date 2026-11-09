# Project #4 — Time-of-day AV/HV traffic simulation (v3)

`av_traffic_sim_tod.py` simulates one day on the same 10-node / 17-edge network as `../v2_failure_mode_2`. The difference is
that demand follows an **hourly profile** instead of 100 cars looping all day. Human-driven and AV demand have
separate peaks. Congestion builds up at those peaks, and the incident and depot-outage rows of the Failure Mode Table
are layered on top.

`../v2_failure_mode_2/` is left unchanged. v3 numbers are **not directly comparable** with v2 because the demand model,
freeway speeds and row-2 edge set all changed (see "Changes from v2").

Tags used in the code and below: **[DOC]** Failure Mode Table or Project notes · **[DATA]** computed here from a public
dataset · **[USER]** task spec · **[ASSUMPTION]** chosen for this prototype · **GAP** no defensible source yet.

---

## Quick start

```bash
pip install networkx
python av_traffic_sim_tod.py                          # weekday: baseline (congestion only) vs all hazards
python av_traffic_sim_tod.py --day-type weekend
python av_traffic_sim_tod.py --force 5-6@1020+60      # block Culver City–Downtown 17:00–18:00
python av_traffic_sim_tod.py --outage 6@1020+120      # Downtown depot dark 17:00–19:00
python av_traffic_sim_tod.py --chargers 1,2,4,5 --ports 2   # notes' 4-depot layout, 2 ports each
python av_traffic_sim_tod.py --rain                   # rain day (row 1b)
python av_traffic_sim_tod.py --sweep --sweep-start 1020   # every edge blocked alone, 60 min at 17:00
python av_traffic_sim_tod.py --days 100               # averages over 100 days (~1 s per day)
python av_traffic_sim_tod.py --hazards 2 --days 50    # one table row at a time
python av_traffic_sim_tod.py --calibrate              # peak hourly flow per directed edge
```

| Option | Meaning |
|---|---|
| `--day-type weekday\|weekend` | Picks the hourly profiles; weekend human demand is ×0.81 |
| `--force u-v@start+dur` | Fully block edge u–v (both directions). Turns stochastic hazards off |
| `--outage n@start+dur` | Depot n has no power. Turns stochastic hazards off. Repeat for multi-depot events |
| `--hazards 1,2,4,5,9,10` | Which table rows are sampled in the stochastic run |
| `--rain` | Row 1b: capacity ×0.92 on every edge, incident rates ×2.33 |
| `--chargers`, `--ports` | Depot nodes (default all 10) and ports per depot (default unlimited) |
| `--human-trips`, `--av-requests`, `--n-av` | Demand scale and fleet size |
| `--no-congestion` | Free-flow travel times (BPR off) |
| `--logs PREFIX` | CSV prefix (default `run`) |

Time is minutes from midnight (480 = 08:00, 1020 = 17:00).

---

## What the model does

### Demand: hourly profiles  [DATA]

`demand_profiles.csv` gives the share of a day's trips that start in each hour. `build_profiles.py` rebuilds it from
the 2017 NHTS trip file:

| Profile | Filter (2017 NHTS public trip file) | Sample |
|---|---|---|
| Human, weekday / weekend | LA–Long Beach–Anaheim CBSA (31080), car/SUV/van/pickup, respondent was the driver | 10,601 / 3,515 trips |
| AV, weekday / weekend | Taxi/limo incl. Uber/Lyft (TRPTRANS 17), **all US** | 2,092 / 721 trips |

Weekday human profile, % of daily trips by start hour:

```
00-05   0.5 0.2 0.1 0.1 0.6 1.8
06-11   4.0 9.1 6.7 5.4 5.5 6.0      AM peak 07:00
12-17   6.6 6.4 6.6 6.9 7.4 9.1      PM peak 17:00
18-23   6.1 4.3 3.1 1.8 1.3 0.7
```

The AV (ride-hail) profile peaks later in the evening and stays higher late at night. Weekday: 7.7% at 17:00, ~5%
from 22:00 to midnight. Weekend: highest hour is 22:00 (8.7%).

How the profiles are used:
- **Human trips.** For each hour h, the number of departures is Poisson(4,000 × share_h). Departure minutes are
  uniform within the hour. Origin and destination are uniform over nodes, as in v2. Each trip is its own vehicle: it
  appears at the origin, drives the currently fastest route, and is removed on arrival.
  - Weekend daily total = weekday × **0.81** [DATA]. That is the NHTS LA weekend-day/weekday-day ratio of weighted
    driver trips, assuming 104 weekend days and 261 weekdays per year.
- **AV requests.** Poisson(170 × share_h) ride requests per hour, served by a **fleet of 15 AVs**.
  - Dispatch: the nearest idle AV (by current travel time) that has enough range for pickup + trip + reaching a
    working depot with 10 mi spare. If no depot is working, it must keep 50 mi in hand.
  - The AV drives empty to the pickup, carries the rider, then idles where it dropped off.
  - Below 50 mi it drives to the nearest working depot and charges to full at 6.3 mi/min (1.8 kWh/min × 3.5 mi/kWh,
    [DOC] Waymo breakdown).
  - A request no AV can pick up within 20 min is cancelled ("unserved").
- **Same demand in both runs.** A given seed always produces the same trips, so the baseline and hazard runs differ
  only because of the hazards (common random numbers).

Why these sources:
- **LADOT Traffic Counts Summary** (the dataset you linked) has **no time-of-day data**. Its 12 columns are Primary
  Street, Dir, Cross Street, Type, Dist, Count Date, Day, W/B, E/B, N/B, S/B and Total, which are 24-hour directional
  totals per intersection.
  - 5,953 rows, latest count date Dec 2016.
  - City of Los Angeles only, so Santa Monica, Culver City, West Hollywood and Pasadena (4 of the 10 nodes) are not in
    it.
  - It can't give hourly peaks. At most it could weight edge capacities on City-of-LA corridors (e.g., Sepulveda, La
    Cienega counts), which needs manual street matching.
- **NHTS 2017** is used because its public file identifies the LA metro area. I did not check whether the 2022 public
  file does. 2017 is pre-COVID.
- **Ride-hail as an AV proxy.** No public hourly Waymo data exists. The CPUC deployment reports contain trip
  timestamps and charging-session times, but Waymo's fields are currently redacted (confidentiality claim under
  review). If those become public, they are the right replacement for the AV profile.
- **Noise.** The AV profile rests on as few as 10 sampled trips in the quietest hours. The overnight values are noisy.

### Network

- Same nodes, edges and edge lengths as v2. Edges are now tagged [ASSUMPTION]:
  - **freeway (9):** 1–2 I-10, 2–5 I-405, 5–4 I-405, 5–7 SR-90, 5–6 I-10, 8–6 I-10, 9–6 US-101, 6–10 SR-110/I-5,
    9–10 US-101/SR-134
  - **arterial (8):** the rest
  - 9 freeway edges matches the table's Assumptions!C38. **Check these against what you meant on the sketch.**
- Free-flow speed: freeway 45 mph, arterial 25 mph [ASSUMPTION]. 45 mph is an inter-neighbourhood average including
  surface access, not a posted limit.

### Congestion (row 1c)  [DOC-standard + ASSUMPTION]

- Travel time on a directed edge = free-flow × (1 + 0.15 (q/c)^4), the standard BPR function.
  - q = vehicles that entered the edge in the last 60 min.
  - c = capacity × incident factor × rain factor.
  - A car's time on an edge is fixed when it enters.
- Routing: every minute, all-pairs fastest paths are recomputed on current congested times. Cars re-plan at every
  node.
- Capacity is in **model vehicles/hour**, since one agent stands for many real cars: freeway 30, arterial 12 per
  direction.
  - The 2.5:1 ratio is an assumption.
  - The level was **calibrated** so that weekday baseline freeway delay is ≈ 0.16 min per freeway mile. That is the
    Caltrans D7 Q1 2022 average in table row 1c (23 M veh-h delay / 8.5 B freeway VMT).
  - That figure averages weekends in and I did not verify its speed threshold, so it is an order-of-magnitude target.
    Result: weekday baseline peak-hour travel-time index ≈ 1.42.
- INRIX 2025 was used only as a **check**, not a parameter.
  - LA's three corridors in the US top 25 peak at 7 AM (I-405 NB), 4 PM (US-101 SB) and 5 PM (Pomona Fwy EB). That
    matches the NHTS peaks.
  - LA: 87 hours lost per driver in 2025, down 1% from 2024.
  - "Hours lost" can't be turned into an hourly travel-time index without each corridor's free-flow time, so it was
    not used to calibrate.

### Failure modes

| Row | Hazard | How it's modeled |
|---|---|---|
| 1 | Human incident, reduced capacity | Rate H = 6.62/h region-wide, spread over all 17 edges. One direction affected. Lasts uniform 15–24 min ([DOC] 0.25–0.4 h). 89.7% shoulder: capacity × U(0.81, 0.99). 10.3% in-lane ([DOC] C32): × U(0.35, 0.78) ([DOC] Lindley factors) |
| 1b | Rain day | `--rain`: rows 1–5 × 2.33 ([DOC] I-880: 3.5 vs 1.5 accidents/shift). Capacity × 0.92 is an **[ASSUMPTION]; the HCM factor is a GAP in the table** |
| 1c | Recurring congestion | Emerges from hourly demand + BPR (above) |
| 2 | Human incident, no capacity | H = 0.0208/h over the **9 freeway edges** → 0.00231 per edge-hour, which is exactly column R. Both directions blocked. Duration Normal(60, 20) truncated to 30–120 min, as in v2 |
| 4 | AV incident, reduced capacity | As row 1, H = 0.156/h |
| 5 | AV incident, no capacity | As row 2, H = 0.000411/h over freeway edges |
| 9 | Depot outage, unplanned | 0.9037/yr per depot, Exp(mean 107 min) ([DOC] SCE). Interrupts charging; AVs re-route to another depot |
| 10 | Depot outage, major event day | 0.1834/yr per depot, Exp(mean 517 min). Sampled **independently** per depot; for correlated multi-depot events use `--outage` |
| 11, 12 | Planned outage, PSPS | Forced scenarios via `--outage` (one or several depots). PSPS q is still a GAP |

- **Exposure by hour.** Incident rates follow exposure: rate in hour h = H × 24 × (share of daily VMT in hour h).
  Human rows use the NHTS LA VMT profile; AV rows use the AV trip profile. The daily total still equals H × 24, so
  incidents cluster in the peaks without changing the table's annual rate.
- **Per-edge rate.** It is H / (number of applicable edges **in this graph**), not column R (which divides by the
  table's assumed 15 edges). This keeps the region-wide rate equal to the table's. It also removes v2's rate caveat:
  v2 applied the row-2 rate to all 17 edges, about 1.9× the table total.

---

## Results (seed 1 unless stated)

**Peaks matter.** In the single-edge sweep, the same 60-minute block costs very different amounts depending on the
hour:

| Edge blocked 60 min | at 03:00 | at 08:00 | at 17:00 |
|---|---|---|---|
| Culver City – LAX (fwy) | +60 min delay | +3,303 | +6,481 |
| Culver City – Downtown LA (fwy) | < +10 | +3,964 | +5,344 |
| West Hollywood – Hollywood (art) | < +10 | +2,196 | +3,067 |

**100 weekdays, all stochastic rows (seeds 0–99):**

| Metric | Baseline (congestion only) | With hazards | Difference |
|---|---|---|---|
| Human trips completed | 3,993 | 3,993 | 0 |
| Total human delay (min/day) | 16,153 | 18,059 | +1,906 (+12%) |
| Minutes stuck on blocked edges | 0 | 195 | +195 |
| AV requests served / unserved | 167 / 0 | 167 / 0 | 0 |
| AV mean wait (min) | 6.58 | 6.74 | +0.15 |
| AV share of VMT | 5.1% | 5.1% | — |
| Peak-hour TTI | 1.42 | 1.44 | +0.02 |

- Events per day match the table: row 1 159 (expected 6.62 × 24 = 159), row 2 0.46 (expected 0.50), row 4 3.7
  (expected 3.75), row 9 0.02 (expected 0.025).
- **Rows one at a time (50 weekdays each):** row 1 adds ~1,040 min/day of delay, row 2 ~970, row 4 ~25.
  - Frequent minor incidents cost about as much total delay as rare full blockages.
  - Row 2's average rests on ~0.5 events/day, so it is the noisier of the two.

**Depots.** With a 180-mi range and ~10-mi trips, each AV charges about once a day (≈20 sessions/day for 15 AVs). A
single depot dark for 2 h barely matters, even with only 4 depots. Making all four of the notes' depots
(`--chargers 1,2,4,5`) dark for 10 h from 10:00 drops service from 173 to 116 served trips (54 unserved). The power
rows matter when outages are **long or correlated** (rows 10, 12), not routine ones.

---

## Outputs

- **Printed:** baseline and hazard summaries, an hour-by-hour comparison table, and the list of blockages/outages.
- **CSV logs** (hazard run): `_trips`, `_av_requests`, `_events` (every incident, including row 1/4 capacity
  factors), `_charges`, `_hourly`.

| Metric | Meaning |
|---|---|
| `human_total_delay_min` | Σ (actual − empty-network fastest time). The baseline is now > 0 because of congestion. Compare runs by the **difference** |
| `human_trips_rerouted` | Trips whose route changed. Now includes congestion re-routing, so the baseline is > 0 |
| `av_unserved` | Requests cancelled after 20 min without a pickup |
| `av_open_at_end_of_day` | Requests still waiting or riding at midnight |
| `av_empty_mile_share` | Empty miles (to pickup or depot) / all AV miles |
| `fwy_delay_min_per_mi` | Calibration check against the Caltrans D7 figure |
| `peak_hour_tti` | Highest hourly mean of (edge time / free-flow time) |

---

## Changes from v2

- Demand model: per-trip humans and a dispatched AV fleet, instead of 100 looping cars with 60-min dwell.
- Freeway edges at 45 mph (v2: all 25 mph).
- Row 2 restricted to freeway edges; per-edge rates computed from H.
- First-edge timing fixed so free-flow trips take exactly their free-flow time.
- AV range is checked before accepting a trip, so the v2 "strand at 51 mi" case can't happen.

---

## Known limitations

- **Origins and destinations are uniform.** The gravity model from the notes isn't used yet; `Params.node_weights`
  is ready for node weights.
- **Model scale.** Capacities are calibrated to one aggregate target. Per-edge capacities would need PeMS station
  flows (freeway edges) or LADOT counts (City-of-LA arterials).
- **Edge timing.** Travel time is fixed when a car enters an edge. A new incident only affects cars already on the
  edge if it fully blocks it.
- **Weekend AV demand** is kept at the weekday total. No LA source for the ratio was found.
- **Row 10** depot outages are independent per depot. Real major-event-day outages are correlated (see
  `outage_sim.py`).
- **One-day horizon.** Rows 13–18 last days to months, which needs a multi-day run or a "starts the day closed"
  scenario.
