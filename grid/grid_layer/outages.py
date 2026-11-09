"""
outages.py -- WHEN routine (background) failures happen.

Each feeder line is a two-state Markov component: it fails at rate lambda and
is repaired after an exponential time with mean CAIDI. The per-line rate is
calibrated so the whole feeder reproduces SCE's SAIFI.

Output: a list of Outage events (element, start hour, end hour, cause) over a
simulation horizon. layer.py turns these into hour-by-hour states.
"""

from dataclasses import dataclass

import numpy as np

from . import params as P


@dataclass(frozen=True)
class Outage:
    element: str          # "line", "bus" or "substation"
    index: int            # line or bus index (-1 for substation)
    start_h: float        # hours from the start of the simulation
    end_h: float
    cause: str            # e.g. "unplanned", "PSPS", "earthquake"

    def active_in_hour(self, h):
        """True if out for any part of hour [h, h+1)."""
        return self.start_h < h + 1 and self.end_h > h


def calibrate_line_rate(feeder, saifi):
    """
    On a radial feeder, line l failing interrupts everyone downstream, so
        SAIFI = sum_l lambda_l * (share of customers downstream of l).
    With one common rate:  lambda_line = SAIFI / sum_l share_l.
    Customers are weighted by load (kW) -- the test feeder has no customer counts.
    Returns (lambda per line per year, {line: downstream share}).
    """
    total = sum(feeder.customer_load.values())
    all_b = set(feeder.buses)
    shares = {}
    for ln in feeder.normal_lines:
        lost = all_b - feeder.energized(feeder.normal_lines - {ln})
        shares[ln] = sum(feeder.customer_load.get(b, 0.0) for b in lost) / total
    return saifi / sum(shares.values()), shares


class RoutineOutages:
    """Background line failures for every enabled class in params.ROUTINE_OUTAGE_CLASSES."""

    def __init__(self, feeder, classes=None):
        classes = classes or P.ROUTINE_OUTAGE_CLASSES
        self.feeder = feeder
        self.lines = sorted(feeder.normal_lines)
        self.classes = {}
        self.shares = {}
        for name, c in classes.items():
            if not c.get("enabled", True):
                continue
            lam_yr, self.shares = calibrate_line_rate(feeder, c["saifi"])
            self.classes[name] = {"lam_per_h": lam_yr / P.HOURS_PER_YEAR,
                                  "lam_per_yr": lam_yr,
                                  "mttr_h": c["caidi_min"] / 60.0,
                                  "saifi": c["saifi"], "caidi_min": c["caidi_min"]}

    def sample(self, horizon_h, rng):
        """
        Alternating renewal process per line and class over [0, horizon_h]:
        exponential up-times (mean 1/lambda), exponential down-times (mean CAIDI),
        starting in steady state so hour 0 is not artificially 'all healthy'.
        """
        events = []
        for cause, c in self.classes.items():
            lam, mttr = c["lam_per_h"], c["mttr_h"]
            u = lam / (lam + 1.0 / mttr)                  # steady-state unavailability
            for ln in self.lines:
                t = 0.0
                if rng.random() < u:                      # already down at t = 0
                    d = rng.exponential(mttr)             # memoryless remaining time
                    events.append(Outage("line", ln, 0.0, min(d, horizon_h), cause))
                    t = d
                while True:
                    t += rng.exponential(1.0 / lam)       # time until next failure
                    if t >= horizon_h:
                        break
                    d = rng.exponential(mttr)
                    events.append(Outage("line", ln, t, min(t + d, horizon_h), cause))
                    t += d
        return events

    def describe(self):
        """Calibrated parameters, for reporting."""
        rows = []
        for name, c in self.classes.items():
            rows.append({"class": name, "saifi": c["saifi"], "caidi_min": c["caidi_min"],
                         "lambda_per_line_per_yr": round(c["lam_per_yr"], 4),
                         "line_failures_per_yr_feeder": round(c["lam_per_yr"] * len(self.lines), 2),
                         "p_any_failure_in_a_day": round(
                             1 - np.exp(-c["lam_per_yr"] * len(self.lines) / 365), 4)})
        return rows
