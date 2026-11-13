# Analysis behind the advisor slides (Nov 2026)

Every number and figure in the slide guide comes from the scripts in this folder, run on `../av_traffic_sim_tod.py`
as committed. The results are saved in `results/`, so the figures can be rebuilt without rerunning the simulations.

| Script | What it runs | Output | Time (2 cores) |
|---|---|---|---|
| `run_experiments.py` | ~1,450 simulated days: 100-day baselines and hazard runs (all rows, then rows 1, 2, 4 alone), 20-day hourly baselines (weekday + weekend), the edge × hour closure sweep (17 edges × 12 start hours × 3 days), the depot-outage grid (notes' 4 depots, every combination of 1–4 dark, 2–12 h, 3 days), and the 10-day all-depots-dark run | `results/experiments.json` | ~25 min |
| `siting_check.py` | All 210 four-depot layouts, 2 normal weekdays each (uniform demand, no hazards) | `results/siting_check.json` | ~4 min |
| `robustness_checks.py` | Slide 8 checks: depot outages with 1–2 ports per depot, and with 4× AV demand | printed | ~5 min |
| `make_figures.py` | Rebuilds every figure from `results/` and writes the quoted numbers to `results/numbers.json` | `figures/*.png`, `results/numbers.json` | ~1 min |

```bash
python run_experiments.py      # optional: results/ is already committed
python siting_check.py         # optional
python make_figures.py
# the two diagrams (fig02, fig05) are Mermaid:
mmdc -i diagrams/architecture.mmd -o figures/fig02_architecture.png -w 2000 -b white -s 2 -c diagrams/mermaid_config.json
mmdc -i diagrams/day_loop.mmd     -o figures/fig05_day_loop.png     -w 2000 -b white -s 2 -c diagrams/mermaid_config.json
```

Requires networkx and matplotlib; `make_figures.py` also reads `grid/outputs/hosting_capacity.csv`.

## Figures

| File | Slide | Shows |
|---|---|---|
| `fig01_network.png` | 3 | The 10-node / 17-edge network in the layout of the notes' sketch |
| `fig02_architecture.png` | 2 | Hazard → traffic + grid layers; coupling still to build |
| `fig03_demand_profiles.png` | 4 | Hourly human and ride-hail demand (NHTS 2017) |
| `fig05_day_loop.png` | 5 | The five steps of each simulated minute |
| `fig06_congestion_by_hour.png` | 5 | Baseline trips and travel-time index by hour |
| `fig07_sweep_heatmap.png` | 6 | Extra delay from a 60-min closure of each edge at each hour |
| `fig08_hazard_contributions.png` | 7 | Extra delay by hazard row, 100 weekdays, 95% CI |
| `fig09_depot_outage_grid.png` | 8 | AV requests lost vs. number of dark depots and outage length |
| `fig09b_av_service_outage.png` | 8 | AV service by hour with all four depots dark 10:00–20:00 |
| `fig14_siting_check.png` | 9 | All 210 four-depot layouts ranked by AV wait; the notes' layout is #200 |
| `fig10_coverage.png` | 10 | Failure Mode Table rows covered so far |
| `fig12_grid_coupling.png` | 10 | Grid layer example: depot demand vs. deliverable MW |
| `fig13_rate_validation.png` | B1 | Simulated event rates vs. the table |
| `fig11_grid_hosting.png` | B2 | Hosting capacity by feeder bus |

## Caveats that apply to all results here

- Trip origins and destinations are uniform; the gravity model from the notes is not in yet.
- Capacities are calibrated to one aggregate target (Caltrans D7 freeway delay per mile).
- Runs are one day long, which understates long or multi-day outages (see Slide 8).
- The default simulation puts a charger at every node. Slides 6 and 7 used that default; Slide 8 and the siting check
  set the chargers explicitly.
