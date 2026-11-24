"""Depot-outage robustness checks quoted on Slide 8 (port limits, 4x AV demand)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import itertools, statistics as st
from av_traffic_sim_tod import Sim, Params, load_profiles
P = load_profiles(); C4 = frozenset((1, 2, 4, 5))

print("--- 2 or 3 of 4 depots dark 10 h, by ports per depot ---")
for ports in (None, 2, 1):
    for k in (2, 3):
        vals = []
        for seed in range(3):
            b = Sim(Params(chargers=C4, ports_per_charger=ports), seed, hazards_on=False, profiles=P).run().summary()
            for combo in itertools.combinations(sorted(C4), k):
                s = Sim(Params(chargers=C4, ports_per_charger=ports, forced_outages=[(n, 600, 600) for n in combo]), seed, hazards_on=False, profiles=P).run().summary()
                vals.append(100 * (s["av_unserved"] - b["av_unserved"]) / b["av_requests"])
        print("ports", ports, "dark", k, "10h: extra lost %", round(st.mean(vals), 1), "max", round(max(vals), 1), "base unserved", b["av_unserved"], "base wait", b["av_mean_wait_min"])

print("--- 4x AV demand (680 requests, 60 AVs), seed 0 ---")
for req, nav in ((680, 60),):
    for ports in (None, 2):
        b = Sim(Params(chargers=C4, ports_per_charger=ports, av_requests_per_day=req, n_av=nav), 0, hazards_on=False, profiles=P).run().summary()
        print("req", req, "nav", nav, "ports", ports, "base", {k: b[k] for k in ("av_unserved", "av_mean_wait_min", "av_share_of_vmt", "av_charge_events")})
        for k in (3, 4):
            combo = (1, 2, 5, 4)[:k]
            s = Sim(Params(chargers=C4, ports_per_charger=ports, av_requests_per_day=req, n_av=nav, forced_outages=[(n, 600, 600) for n in combo]), 0, hazards_on=False, profiles=P).run().summary()
            print("   dark", combo, "lost %", round(100 * (s["av_unserved"] - b["av_unserved"]) / b["av_requests"], 1), "wait", s["av_mean_wait_min"])
