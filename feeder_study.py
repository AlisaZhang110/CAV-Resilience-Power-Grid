"""
Feeder study starter: AV charging depots on the IEEE 33-bus (Baran & Wu) feeder.

Run:  pip install pandapower
      python feeder_study.py

What it does
  1. Base case: power flow on the unmodified feeder.
  2. Hosting capacity: for each candidate depot bus (one at a time), raise depot
     load in 0.1 MW steps until a voltage or thermal limit is violated.
  3. N-1 (single-outage) check: with depots sized per DEPOT_MW_N1, take each in-service
     line out one at a time, re-run power flow, and record:
       - which buses / depots lose supply (radial feeder -> downstream is dropped)
       - whether closing one of the 5 normally-open tie lines restores them,
         and whether that restored configuration respects the limits.

ASSUMPTIONS (change these; they are not from the test case):
  - The test case ships with no line ratings (max_i_ka = 99999), so thermal
    limits below are invented placeholders: trunk 0.30 kA, all others 0.15 kA.
  - Substation (slack) voltage set to 1.05 p.u., as if the substation
    transformer's tap changer is regulating high. At the test case's default
    1.00 p.u. the unmodified feeder already sags to 0.913 p.u., i.e. it fails a
    0.95 p.u. limit before any depot is added.
  - Voltage limits 0.95-1.05 p.u. (ANSI C84.1 Range A is +/-5%).
  - Depot power factor 0.95 lagging.
"""

import copy
import warnings
import numpy as np
import pandas as pd
import pandapower as pp
import pandapower.networks as pn
import pandapower.topology as top

warnings.filterwarnings("ignore")

# ---------------- parameters ----------------
V_MIN = 0.95            # p.u.
SUB_V = 1.05            # p.u. substation setpoint (assumption)
V_MAX = 1.05            # p.u.
LOADING_MAX = 100.0     # % of line rating
TRUNK_LINES = [0, 1, 2, 3, 4]          # substation -> bus 5 (pandapower indices)
TRUNK_RATING_KA = 0.30
OTHER_RATING_KA = 0.15
DEPOT_BUSES = {"D_mid_trunk": 5, "D_feeder_end": 17,
               "D_strong_lateral": 21, "D_weak_lateral": 32}
# Depot sizes for the N-1 study, chosen so the N-0 (all lines in) case passes.
# Note how small the feeder-end depot has to be: that is the hosting-capacity result.
DEPOT_MW_N1 = {"D_mid_trunk": 0.3, "D_feeder_end": 0.05,
               "D_strong_lateral": 0.5, "D_weak_lateral": 0.1}
PF = 0.95
STEP_MW = 0.1


def build_net():
    net = pn.case33bw()
    net.ext_grid["vm_pu"] = SUB_V
    net.line["max_i_ka"] = OTHER_RATING_KA
    net.line.loc[TRUNK_LINES, "max_i_ka"] = TRUNK_RATING_KA
    return net


def add_depot(net, bus, p_mw, name):
    q = p_mw * np.tan(np.arccos(PF))
    return pp.create_load(net, bus, p_mw=p_mw, q_mvar=q, name=name)


def check(net):
    """Run power flow; return dict of results and violations (energized buses only)."""
    try:
        pp.runpp(net, numba=False)
    except pp.LoadflowNotConverged:
        return {"converged": False, "v_min": np.nan, "max_loading": np.nan, "ok": False}
    vm = net.res_bus.vm_pu.dropna()
    loading = net.res_line.loading_percent.dropna()
    v_min, v_max, max_ld = vm.min(), vm.max(), loading.max()
    ok = (v_min >= V_MIN) and (v_max <= V_MAX) and (max_ld <= LOADING_MAX)
    binding = []
    if v_min < V_MIN:
        binding.append(f"undervoltage @ bus {vm.idxmin()}")
    if max_ld > LOADING_MAX:
        binding.append(f"overload @ line {loading.idxmax()}")
    return {"converged": True, "v_min": v_min, "max_loading": max_ld,
            "ok": ok, "binding": "; ".join(binding)}


def base_case():
    net = build_net()
    r = check(net)
    print(f"Base case: min V = {r['v_min']:.3f} p.u., max line loading = "
          f"{r['max_loading']:.1f}%  (load = {net.load.p_mw.sum():.2f} MW)")


def hosting_capacity():
    rows = []
    for name, bus in DEPOT_BUSES.items():
        p = 0.0
        last_ok = 0.0
        binding = ""
        while p < 10.0:
            p = round(p + STEP_MW, 3)
            net = build_net()
            add_depot(net, bus, p, name)
            r = check(net)
            if not r["ok"]:
                binding = r.get("binding", "no convergence")
                break
            last_ok = p
        rows.append({"depot": name, "bus": bus, "hosting_capacity_MW": last_ok,
                     "limit_hit_at_MW": p, "binding_constraint": binding})
    df = pd.DataFrame(rows)
    print("\nHosting capacity (each depot alone, all others absent):")
    print(df.to_string(index=False))
    return df


def n_minus_1():
    net0 = build_net()
    for name, bus in DEPOT_BUSES.items():
        add_depot(net0, bus, DEPOT_MW_N1[name], name)
    tie_lines = list(net0.line.index[~net0.line.in_service])
    normal_lines = list(net0.line.index[net0.line.in_service])

    r0 = check(net0)
    print(f"\nN-0 with depots at {DEPOT_MW_N1} MW: min V = {r0['v_min']:.3f}, "
          f"max loading = {r0['max_loading']:.1f}%, ok = {r0['ok']}")

    rows = []
    for ln in normal_lines:
        net = copy.deepcopy(net0)
        net.line.at[ln, "in_service"] = False
        lost = top.unsupplied_buses(net)
        depots_lost = [n for n, b in DEPOT_BUSES.items() if b in lost]
        r = check(net)  # dropped buses come back as NaN and are ignored

        best = None
        if lost:
            # try closing each tie line by itself; keep the best restoring option
            for tie in tie_lines:
                trial = copy.deepcopy(net)
                trial.line.at[tie, "in_service"] = True
                if top.unsupplied_buses(trial):
                    continue
                rt = check(trial)
                if best is None or (rt["ok"], rt["v_min"]) > (best[1]["ok"], best[1]["v_min"]):
                    best = (tie, rt)

        rows.append({
            "line_out": ln,
            "from-to": f"{net.line.at[ln,'from_bus']}-{net.line.at[ln,'to_bus']}",
            "buses_dropped": len(lost),
            "depots_dropped": ",".join(depots_lost) or "-",
            "v_min_after": round(r["v_min"], 3),
            "ok_without_switching": r["ok"] and not lost,
            "best_tie": "-" if best is None else int(best[0]),
            "v_min_with_tie": "-" if best is None else round(best[1]["v_min"], 3),
            "ok_with_tie": "-" if best is None else best[1]["ok"],
        })
    df = pd.DataFrame(rows)
    print("\nN-1 results (one line out at a time):")
    print(df.to_string(index=False))

    n = len(df)
    n_drop = (df.buses_dropped > 0).sum()
    n_restored_ok = (df.ok_with_tie == True).sum()
    print(f"\nSummary: {n} single-line outages; {n_drop} drop load (radial feeder). "
          f"A single tie closure restores all load within limits in {n_restored_ok} of them.")
    return df


if __name__ == "__main__":
    base_case()
    hc = hosting_capacity()
    n1 = n_minus_1()
    hc.to_csv("hosting_capacity.csv", index=False)
    n1.to_csv("n_minus_1.csv", index=False)
