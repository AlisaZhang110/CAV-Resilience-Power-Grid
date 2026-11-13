"""Runs every simulation behind the slide figures (~1,450 runs; ~25 min on 2 cores)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import json, itertools
from multiprocessing import Pool
from av_traffic_sim_tod import Sim, Params, EDGES, NODES, load_profiles
PROF = load_profiles()
OUT = HERE / "results" / "experiments.json"

def run(job):
    kind, seed, kw, haz = job
    p = Params(**kw)
    s = Sim(p, seed, hazards_on=haz, profiles=PROF).run()
    sm = s.summary()
    out = dict(kind=kind, seed=seed, kw={k: (list(v) if isinstance(v, (tuple, frozenset)) else v) for k, v in kw.items()}, haz=haz, summary=sm)
    if kind in ("hourly", "all", "avsvc", "avsvc_base", "base"):
        out["hourly"] = s.hourly_rows()
    if kind == "all":
        out["event_hours"] = [(e["row"], e["start_min"] // 60) for e in s.event_log]
    return out

jobs = []
for seed in range(100):
    jobs.append(("base", seed, {}, False))
    jobs.append(("all", seed, {}, True))
    for r in ("1", "2", "4"):
        jobs.append(("row" + r, seed, {"hazards": (r,)}, True))
for dt in ("weekday", "weekend"):
    for seed in range(20):
        jobs.append(("hourly", seed, {"day_type": dt}, False))
for seed in range(3):
    for (u, v, c) in EDGES:
        for h in range(0, 24, 2):
            jobs.append(("sweep", seed, {"forced_blocks": [(u, v, h * 60, 60)]}, False))
C4 = (1, 2, 4, 5)
for seed in range(3):
    jobs.append(("dep_base", seed, {"chargers": frozenset(C4)}, False))
    for k in range(1, 5):
        for combo in itertools.combinations(C4, k):
            for dur_h in (2, 4, 6, 8, 10, 12):
                jobs.append(("dep", seed, {"chargers": frozenset(C4), "forced_outages": [(n, 600, dur_h * 60) for n in combo]}, False))
for seed in range(10):
    jobs.append(("avsvc_base", seed, {"chargers": frozenset(C4)}, False))
    jobs.append(("avsvc", seed, {"chargers": frozenset(C4), "forced_outages": [(n, 600, 600) for n in C4]}, False))
# note: avsvc_base needs hourly too
if __name__ == "__main__":
    print(len(jobs), "jobs", flush=True)
    res = []
    with Pool(2) as pool:
        for i, r in enumerate(pool.imap_unordered(run, jobs, chunksize=4)):
            res.append(r)
            if i % 100 == 0:
                print(i, flush=True)
    json.dump(res, open(OUT, "w"), default=str)
    print("done", flush=True)
