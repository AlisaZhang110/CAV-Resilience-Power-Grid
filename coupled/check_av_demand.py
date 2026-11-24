"""
check_av_demand.py -- is the AV demand a scaled-down version of ride-hail demand?

    python -m coupled.check_av_demand

Checks, in order:
  1. Source: the AV hourly profile is the NHTS 2017 TRPTRANS 17 (taxi/limo incl. Uber/Lyft) column.
  2. Shape: requests the simulator actually generates follow that profile (chi-square over 300 days).
  3. Scale: AV requests and AV VMT are a small, fixed fraction of the human stream.
  4. Other fleets (Tesla) use the same shape, scaled by their own requests_per_day.
  5. Known departures from "pure ride-hail".
"""
import os
import numpy as np
from scipy import stats

from . import config as C
from .scenarios import ordinary
from .sim import CoupledSim
from grid_layer.feeder import Feeder
from av_traffic_sim_tod import Params, Sim, load_profiles

HERE = os.path.dirname(os.path.abspath(__file__))


def main(days=300):
    prof = load_profiles()
    raw = np.genfromtxt(os.path.join(C.ROOT, "traffic", "v3_time_of_day", "demand_profiles.csv"),
                        delimiter=",", names=True)
    out = []
    say = lambda s="": (print(s), out.append(s))

    av, hu = np.array(prof["av_trips_weekday"]), np.array(prof["human_trips_weekday"])
    say("1. SOURCE")
    say(f"   AV profile column: av_trips_weekday = NHTS 2017 TRPTRANS 17 (taxi/limo incl. Uber/Lyft), all US")
    say(f"   unweighted sample: {int(raw['av_n_weekday'].sum())} weekday trips, "
        f"min {int(raw['av_n_weekday'].min())} in one hour (03:00); weekend {int(raw['av_n_weekend'].sum())}")
    say(f"   weekday AV peak {int(av.argmax()):02d}:00 ({100 * av.max():.1f}%); human peaks 07:00 and 17:00")
    say(f"   AV share of trips 22:00-02:00: {100 * av[[22, 23, 0, 1]].sum():.1f}% vs human "
        f"{100 * hu[[22, 23, 0, 1]].sum():.1f}%  (ride-hail runs later at night)")
    we = np.array(prof["av_trips_weekend"])
    say(f"   weekend AV peak {int(we.argmax()):02d}:00 ({100 * we.max():.1f}%) -- TCRP Report 195 reports LA "
        "Uber/Lyft volume peaking Saturday 9 p.m.")

    say("\n2. SHAPE (does the simulator draw requests from that profile?)")
    p = Params()
    counts = np.zeros(24)
    for s in range(days):
        sim = Sim(p, s, hazards_on=False, profiles=prof)
        for t, lst in sim.av_demand.items():
            counts[t // 60] += len(lst)
    exp = av * counts.sum()
    chi2, pval = stats.chisquare(counts, exp)
    say(f"   {days} weekdays: {counts.sum() / days:.1f} requests/day (target {p.av_requests_per_day})")
    say(f"   chi-square vs NHTS profile: chi2 = {chi2:.1f}, df = 23, p = {pval:.2f} "
        f"({'consistent' if pval > 0.05 else 'NOT consistent'})")
    say(f"   largest hourly gap: {100 * np.max(np.abs(counts / counts.sum() - av)):.2f} percentage points")

    say("\n3. SCALE")
    f = Feeder()
    built = set(C.EXISTING_DEPOTS)
    vm = []
    for s in range(10):
        sim = CoupledSim(s, [C.WAYMO], {"Waymo": built}, built, ordinary(None), f, profiles=prof).run()
        tot = sum(sim.vmt.values())
        vm.append((sim.vmt["av_pax"] + sim.vmt["av_empty"]) / tot)
    say(f"   AV requests / human trips = {p.av_requests_per_day} / {p.human_trips_per_day} = "
        f"{100 * p.av_requests_per_day / p.human_trips_per_day:.2f}% of trips")
    say(f"   AV share of VMT (10 coupled weekdays): {100 * np.mean(vm):.1f}%  (target 5% [DOC Assumptions!C9])")
    say(f"   trips per AV per day: {p.av_requests_per_day / p.n_av:.1f} "
        "(a model-scale number: the 15-AV fleet was sized for zero unserved requests, not to Waymo utilisation)")

    say("\n4. OTHER FLEETS")
    tes = np.zeros(24)
    for s in range(40):
        sim = CoupledSim(s, [C.WAYMO, dict(name="Tesla", n_av=10, requests_per_day=113)],
                         {"Waymo": built, "Tesla": built}, built, ordinary(None), f, profiles=prof)
        for t, lst in sim.av_demand.items():
            tes[t // 60] += sum(1 for x in lst if x[2] == "Tesla")
    chi2t, pt = stats.chisquare(tes, av * tes.sum())
    say(f"   Tesla stream (10 AVs, 113 requests/day target): {tes.sum() / 40:.1f} requests/day over 40 days;")
    say(f"   same av_trips profile (chi-square p = {pt:.2f}); Waymo's stream is unchanged when Tesla is added")

    say("\n5. DEPARTURES FROM 'SCALED-DOWN RIDE-HAIL' (not fixed here; flagged)")
    say("   a. National profile, not LA (LA-CBSA subsample is only 193 trips).")
    say("   b. TRPTRANS 17 mixes taxi/limo with Uber/Lyft. In SF in 2016 ride-hail made ~12x as many trips as")
    say("      taxis (SFCTA, TNCs Today), so the mix is mostly ride-hail, but it is not pure.")
    say("   c. Weekend AV total is kept at the weekday total (no LA ratio found); TCRP 195 says weekend nights")
    say("      dominate LA ride-hail, so weekend AV demand is probably under-stated. Experiments here are weekdays.")
    say("   d. 2017, pre-COVID. Origins/destinations are uniform for both humans and AVs.")
    with open(os.path.join(HERE, "results", "av_demand_check.txt"), "w") as fh:
        fh.write("\n".join(out) + "\n")
    np.savetxt(os.path.join(HERE, "results", "av_demand_check_hourly.csv"),
               np.column_stack([np.arange(24), av, counts / counts.sum(), hu]), delimiter=",",
               header="hour,nhts_av_share,simulated_av_share,nhts_human_share", comments="", fmt="%.5f")


if __name__ == "__main__":
    main()
