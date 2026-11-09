"""
run_examples.py -- how to use the grid layer, scenario by scenario.

Run:   python run_examples.py
Writes CSVs to ./outputs/ (the folder is created next to this script).

Scenarios
  0. Calibration + validation of the routine outage model
  1. Planning studies: hosting capacity and N-1 (with deliverable MW per depot)
  2. An ordinary week (routine random failures only)
  3. PSPS: wildfire-zone shutoff for 30 hours
  4. Earthquake: substation loss for 8 hours
  5. Storm damage: two specific lines down for 12 hours
  6. Coupled loop: how the transportation layer talks to the grid each hour
"""

from pathlib import Path

import pandas as pd

from grid_layer import GridLayer, HazardEvent, psps, substation_loss
from grid_layer import studies

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 20)
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(exist_ok=True)


def save(run, name):
    run.summary().to_csv(OUT / f"{name}_summary.csv", index=False)
    run.bus_table().to_csv(OUT / f"{name}_bus_states.csv", index=False)
    run.depot_table().to_csv(OUT / f"{name}_depot_states.csv", index=False)


def show_events(run, title):
    print(f"\n=== {title} ===")
    ev = run.periods()
    if ev.empty:
        print("No outages in this run (a random day has ~1 % chance of any line failure).")
    else:
        print(ev.to_string(index=False))


if __name__ == "__main__":
    grid = GridLayer(seed=1)   # one Feeder object is reused, so its cache keeps growing

    # 0 ------------------------------------------------------------------
    print("=== 0. Routine outage model ===")
    print(pd.DataFrame(grid.routine.describe()).to_string(index=False))
    print("Validation:", studies.validate_routine(years=5000, feeder=grid.feeder))

    # 1 ------------------------------------------------------------------
    hc = studies.hosting_capacity(grid.feeder)
    n1 = studies.n_minus_1(grid.feeder)
    hc.to_csv(OUT / "hosting_capacity.csv", index=False)
    n1.to_csv(OUT / "n_minus_1.csv", index=False)
    print("\n=== 1. Planning studies (saved to outputs/) ===")
    print("Hosting capacity at depot buses:")
    print(hc[hc.bus.isin([5, 17, 21, 32])].to_string(index=False))
    print("N-1 cases where every depot has power but some are curtailed:")
    print(n1[(n1.depot_supply_frac < 1) & (n1.buses_dark_after == 0)].to_string(index=False))

    # 2 ------------------------------------------------------------------
    run = grid.simulate(n_days=7)
    save(run, "ordinary_week")
    show_events(run, "2. Ordinary week (routine failures only)")

    # 3 ------------------------------------------------------------------
    run = grid.simulate(n_days=2, hazards=[psps(start_h=10, duration_h=30)])
    save(run, "psps")
    show_events(run, "3. PSPS in the WUI zone, hour 10 to hour 40")

    # 4 ------------------------------------------------------------------
    run = grid.simulate(n_days=1, hazards=[substation_loss(start_h=6, duration_h=8)])
    save(run, "earthquake")
    show_events(run, "4. Substation loss (earthquake), 06:00-14:00")

    # 5 ------------------------------------------------------------------
    f = grid.feeder
    storm = HazardEvent("storm", start_h=12, duration_h=12,
                        lines=[f.line_between(2, 3), f.line_between(18, 19)])
    run = grid.simulate(n_days=1, hazards=[storm])
    save(run, "storm")
    show_events(run, "5. Storm damage: lines 2-3 and 18-19, 12:00-24:00")

    # 6 ------------------------------------------------------------------
    print("\n=== 6. Coupled loop (placeholder transportation layer) ===")

    class TransportStub:
        """Stand-in for the fleet model: asks for charging power, receives capacity."""
        def charging_demand(self, t):
            surge = 1.5 if 16 <= t % 24 <= 20 else 1.0      # e.g. evening return-to-depot peak
            return {"D_mid_trunk": 0.30 * surge, "D_feeder_end": 0.05 * surge,
                    "D_strong_lateral": 0.50 * surge, "D_weak_lateral": 0.10 * surge}

        def receive_capacity(self, t, capacity_mw):
            pass   # the real fleet model would queue / reroute AVs here

    fleet = TransportStub()
    grid.reset(n_days=1, hazards=[HazardEvent("storm", 15, 6, lines=[f.line_between(1, 18)])])
    rows = []
    for t in range(grid.horizon_h):
        demand = fleet.charging_demand(t)          # transport -> grid
        state = grid.step(t, depot_demand=demand)  # grid physics
        fleet.receive_capacity(t, state.depot_mw)  # grid -> transport
        rows.append({"hour": t, "lines_down": list(state.lines_down),
                     "ties_closed": list(state.ties_closed),
                     "demand_mw": round(sum(demand.values()), 3),
                     "delivered_mw": round(sum(state.depot_mw.values()), 3)})
    print(pd.DataFrame(rows)[13:23].to_string(index=False))

    print(f"\nCSV files written to: {OUT}")
