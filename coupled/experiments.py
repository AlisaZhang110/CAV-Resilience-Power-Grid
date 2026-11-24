"""
experiments.py -- run the depot-placement and multi-fleet experiments.

    python -m coupled.experiments placement     # base 4 depots + one candidate (Waymo only)
    python -m coupled.experiments fleets        # Waymo + Tesla: exclusive vs universal depots
    python -m coupled.experiments showcase      # hour-by-hour runs used in the time-series figures
    python -m coupled.experiments all

Every configuration sees the same seeds, so the same demand and the same hazard events
(common random numbers): differences between configurations come from the configuration.
Results: coupled/results/<experiment>_runs.csv (one row per simulated day).
"""
import csv
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

from . import config as C

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
SCEN_ORDER = ["ordinary", "rain", "line_fault", "planned", "med", "psps", "fire1", "fire3",
              "flood100", "flood500", "quake", "stall"]
BIG_GRID = ["med", "psps", "fire3", "flood500", "quake"]        # can darken >= 3 nodes
GRID_SCEN = ["line_fault", "planned", "med", "psps", "fire3", "flood100", "flood500", "quake"]
BASE = tuple(C.EXISTING_DEPOTS)

_W = {}


def _init():
    from grid_layer.feeder import Feeder
    from av_traffic_sim_tod import load_profiles
    from .scenarios import build_scenarios
    _W["feeder"] = Feeder()
    _W["prof"] = load_profiles()
    _W["scen"] = build_scenarios(_W["feeder"])


def events_for(key, seed):
    from .scenarios import ordinary
    if key == "ordinary":
        return ordinary(None)
    rng = np.random.default_rng([seed, SCEN_ORDER.index(key)])
    return _W["scen"][key].make(rng)


def run_job(job):
    from .sim import CoupledSim
    C.STALL_ON_DARK_SIGNALS = job.get("stall_on_dark", True)
    ev = events_for(job["scenario"], job["seed"])
    sim = CoupledSim(job["seed"], job["fleets"], job["access"], set(job["built"]), ev,
                     _W["feeder"], signals=job.get("signals", True), profiles=_W["prof"]).run()
    row = {k: job[k] for k in ("experiment", "config", "variant", "scenario", "seed")}
    row.update(job.get("tags", {}))
    row.update({k: round(v, 4) if isinstance(v, float) else v for k, v in sim.metrics().items()})
    if job.get("hourly"):
        row["_hourly"] = sim.hourly_series()
    return row


def placement_jobs(n_ord=30, n_scen=10, start_ord=0, start_scen=0, extras=True):
    jobs = []
    cfgs = [("base", BASE)] + [(f"+{c}", BASE + (c,)) for c in C.CANDIDATE_SITES]
    for name, built in cfgs:
        for scen in SCEN_ORDER:
            rng_s = range(start_ord, start_ord + n_ord) if scen == "ordinary" else range(start_scen, start_scen + n_scen)
            for s in rng_s:
                jobs.append(dict(experiment="placement", config=name, variant="main", scenario=scen, seed=s,
                                 built=built, fleets=[C.WAYMO], access={"Waymo": built},
                                 tags=dict(new_site=name[1:] if name != "base" else "")))
        for scen in BIG_GRID:                               # sensitivity: no dark-signal fleet stall
            for s in range(start_scen, start_scen + n_scen):
                jobs.append(dict(experiment="placement", config=name, variant="no_row7_trigger", scenario=scen,
                                 seed=s, built=built, fleets=[C.WAYMO], access={"Waymo": built},
                                 stall_on_dark=False, tags=dict(new_site=name[1:] if name != "base" else "")))
    for scen in GRID_SCEN if extras else []:                # dark-signal coupling off, base layout
        for s in range(start_scen, start_scen + n_scen):
            for sig in (True, False):
                jobs.append(dict(experiment="placement", config="base",
                                 variant="signals_on" if sig else "signals_off", scenario=scen, seed=s,
                                 built=BASE, fleets=[C.WAYMO], access={"Waymo": BASE}, signals=sig,
                                 stall_on_dark=False, tags=dict(new_site="")))
    return jobs


def fleet_jobs(n_ord=15, n_scen=6, scen=("line_fault", "med", "psps", "quake")):
    jobs = []
    for nt in C.TESLA_SIZES:
        tesla = dict(name="Tesla", n_av=nt, requests_per_day=round(C.WAYMO["requests_per_day"] * nt / C.WAYMO["n_av"]))
        fleets = [C.WAYMO, tesla]
        cfgs = [("shared_existing", "universal", "", BASE, {"Waymo": BASE, "Tesla": BASE})]
        for c in C.CANDIDATE_SITES:
            allb = BASE + (c,)
            cfgs.append((f"exclusive+{c}", "exclusive", str(c), allb, {"Waymo": BASE, "Tesla": (c,)}))
            cfgs.append((f"universal+{c}", "universal", str(c), allb, {"Waymo": allb, "Tesla": allb}))
        for name, mode, site, built, acc in cfgs:
            for sc in ("ordinary",) + tuple(scen):
                for s in range(n_ord if sc == "ordinary" else n_scen):
                    jobs.append(dict(experiment="fleets", config=f"T{nt}:{name}", variant="main", scenario=sc,
                                     seed=s, built=built, fleets=fleets, access=acc,
                                     tags=dict(tesla_n=nt, mode=mode, new_site=site)))
    return jobs


def showcase_jobs():
    jobs = []
    for scen, seed in (("med", 4), ("psps", 1)):
        for name, built in (("base", BASE), ("+6", BASE + (6,)), ("+10", BASE + (10,))):
            for sig in (True, False):
                jobs.append(dict(experiment="showcase", config=name, variant="signals_on" if sig else "signals_off",
                                 scenario=scen, seed=seed, built=built, fleets=[C.WAYMO],
                                 access={"Waymo": built}, signals=sig, stall_on_dark=False, hourly=True))
    return jobs


def run(name, jobs, procs=2, append=False):
    os.makedirs(RES, exist_ok=True)
    t0 = time.time()
    rows = []
    with Pool(procs, initializer=_init) as pool:
        for i, r in enumerate(pool.imap_unordered(run_job, jobs, chunksize=4)):
            rows.append(r)
            if (i + 1) % 100 == 0:
                print(f"  {name}: {i + 1}/{len(jobs)} days, {time.time() - t0:.0f} s", flush=True)
    if name == "showcase":
        import json
        with open(os.path.join(RES, "showcase_hourly.json"), "w") as f:
            json.dump(rows, f)
        return rows
    path = os.path.join(RES, f"{name}_runs.csv")
    if append and os.path.exists(path):
        old = list(csv.DictReader(open(path)))
        have = {(r["config"], r["variant"], r["scenario"], str(r["seed"])) for r in old}
        rows = old + [r for r in rows if (r["config"], r["variant"], r["scenario"], str(r["seed"])) not in have]
        for r in rows:
            r["seed"] = int(r["seed"])
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, restval="")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["config"], r["variant"], r["scenario"], r["seed"])))
    print(f"{name}: {len(rows)} simulated days in {time.time() - t0:.0f} s -> results/{name}_runs.csv")
    return rows


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("placement", "all"):
        run("placement", placement_jobs())
    if what in ("fleets", "all"):
        run("fleets", fleet_jobs())
    if what in ("showcase", "all"):
        run("showcase", showcase_jobs())
    if what == "placement_more":   # more seeds for the placement ranking (appended)
        run("placement", placement_jobs(n_ord=60, n_scen=15, start_ord=30, start_scen=10), append=True)
