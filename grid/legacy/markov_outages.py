"""
Convert SCE reliability indices (from the Failure Mode Table) into two-state
Markov failure/repair parameters per depot, then sanity-check by simulation.

Two-state model: depot is UP or DOWN.
  UP   -> DOWN at rate lambda (failures per year)   = SAIFI   (interruptions/customer-yr)
  DOWN -> UP   at rate mu     (repairs per year)    = 1/MTTR, with MTTR = CAIDI
  Long-run unavailability U = lambda / (lambda + mu)  ~= SAIFI * CAIDI = SAIDI

Inputs are the 10-yr averages already in your Assumptions/Working sheets.
Approximation: SAIFI is a customer-weighted system average, applied here as if
it were each depot's own rate, with depots independent of each other.
"""

import numpy as np

HOURS_PER_YEAR = 8760.0

OUTAGE_CLASSES = {
    # name: (SAIFI per year, CAIDI in minutes)  <- from your table
    "unplanned (MED excluded)": (0.9037, 107.321),
    "major event day":          (0.1834, 516.914),
    "planned maintenance":      (0.3113, 300.183),
}


def markov_params(saifi, caidi_min, dt_h=1.0):
    lam_h = saifi / HOURS_PER_YEAR          # failures per hour
    mttr_h = caidi_min / 60.0
    mu_h = 1.0 / mttr_h                     # repairs per hour
    p_fail = 1 - np.exp(-lam_h * dt_h)      # P(UP -> DOWN) in one timestep
    p_repair = 1 - np.exp(-mu_h * dt_h)     # P(DOWN -> UP) in one timestep
    unavail = lam_h / (lam_h + mu_h)
    return lam_h, mu_h, p_fail, p_repair, unavail


def simulate_continuous(saifi, caidi_min, years=200_000, seed=0):
    """Alternate exponential up-times and down-times; return down-minutes per year."""
    rng = np.random.default_rng(seed)
    lam_h = saifi / HOURS_PER_YEAR
    mttr_h = caidi_min / 60.0
    t, down, horizon = 0.0, 0.0, years * HOURS_PER_YEAR
    # vectorised in chunks for speed
    while t < horizon:
        n = 100_000
        ups = rng.exponential(1 / lam_h, n)      # inverse-CDF sampling under the hood
        downs = rng.exponential(mttr_h, n)
        t += ups.sum() + downs.sum()
        down += downs.sum()
    return down / (t / HOURS_PER_YEAR) * 60.0


if __name__ == "__main__":
    print(f"{'class':28s} {'lambda/h':>10s} {'mu/h':>7s} {'P(fail)/h':>10s} "
          f"{'P(repair)/h':>11s} {'P(out in 24h)':>13s} {'U*525600 (min/yr)':>18s} "
          f"{'SAIFIxCAIDI':>11s} {'simulated':>9s}")
    for name, (saifi, caidi) in OUTAGE_CLASSES.items():
        lam, mu, pf, pr, U = markov_params(saifi, caidi)
        p_day = 1 - np.exp(-lam * 24)
        sim = simulate_continuous(saifi, caidi)
        print(f"{name:28s} {lam:10.3e} {mu:7.3f} {pf:10.3e} {pr:11.3f} "
              f"{p_day:13.4%} {U*525600:18.1f} {saifi*caidi:11.1f} {sim:9.1f}")

    # Discretization check: with 1-h steps, a geometric repair process has mean
    # duration 1/p_repair hours, which overstates the true MTTR.
    print("\nDiscretization check (1-hour timestep):")
    for name, (saifi, caidi) in OUTAGE_CLASSES.items():
        *_, pr, _ = markov_params(saifi, caidi)
        print(f"  {name:28s} true mean outage {caidi/60:5.2f} h | "
              f"discrete-step mean {1/pr:5.2f} h")
