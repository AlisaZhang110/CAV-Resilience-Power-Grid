"""Preliminary siting check: every 4-depot layout on 2 normal weekdays (uniform demand, no hazards)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import itertools, statistics as st, json
from multiprocessing import Pool
from av_traffic_sim_tod import Sim, Params, load_profiles, NODES
P = load_profiles()
def run(combo):
    out = []
    for seed in range(2):
        s = Sim(Params(chargers=frozenset(combo)), seed, hazards_on=False, profiles=P).run().summary()
        out.append(s)
    m = lambda k: st.mean(x[k] for x in out)
    return dict(combo=combo, wait=m("av_mean_wait_min"), p95=m("av_p95_wait_min"), empty=m("av_empty_mile_share"),
                unserved=m("av_unserved"), served=m("av_served"))
if __name__ == "__main__":
    combos = list(itertools.combinations(range(1, 11), 4))
    with Pool(2) as pool:
        res = pool.map(run, combos)
    json.dump(res, open(HERE / "results" / "siting_check.json", "w"))
    res.sort(key=lambda r: (r["unserved"], r["wait"]))
    nc = next(r for r in res if r["combo"] == (1, 2, 4, 5))
    rank = [r["combo"] for r in res].index((1, 2, 4, 5)) + 1
    print("n placements", len(res))
    for r in res[:5] + res[-5:]:
        print([NODES[n] for n in r["combo"]], {k: round(v, 2) for k, v in r.items() if k != "combo"})
    print("notes Nc", {k: round(v, 2) for k, v in nc.items() if k != "combo"}, "rank", rank)
    w = [r["wait"] for r in res]; e = [r["empty"] for r in res]; u = [r["unserved"] for r in res]
    print("wait range", min(w), max(w), "empty range", min(e), max(e), "unserved range", min(u), max(u))
