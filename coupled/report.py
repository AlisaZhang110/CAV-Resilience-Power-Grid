"""
report.py -- turn experiment results into tables and figures.

    python -m coupled.report            # after `python -m coupled.experiments all`

Writes coupled/results/*_summary.csv, coupled/results/summary.md and coupled/figures/*.png.

Annual weighting (hazard-conditioned sampling, see scenarios.py):
    annual mean = ordinary mean + sum_s rate_s x days_s x (scenario mean - ordinary mean) / 365
Differences between configurations are PAIRED by seed (common random numbers).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

from . import config as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES, FIG = os.path.join(HERE, "results"), os.path.join(HERE, "figures")

# palette: dataviz reference instance, light mode (validated: scripts/validate_palette.js)
SURF, INK, INK2, MUTED, GRID = "#ffffff", "#0b0b0b", "#52514e", "#8a8984", "#e4e3df"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
DIVERGING = LinearSegmentedColormap.from_list(
    "bluegrayred", ["#184f95", "#5598e7", "#cde2fb", "#f0efec", "#f7c9c5", "#e66767", "#a8302f"])
NAMES = {1: "Santa Monica", 2: "Sawtelle", 3: "West Hollywood", 4: "LAX", 5: "Culver City",
         6: "Downtown LA", 7: "Playa del Rey", 8: "Mid-City", 9: "Hollywood", 10: "Pasadena"}
SCEN_LABEL = {"ordinary": "Ordinary weekday", "rain": "Rain day (1b)", "line_fault": "Line fault (9)",
              "planned": "Planned outage (11)", "med": "Major event day (10)", "psps": "PSPS (12)",
              "fire1": "Wildfire, 1 edge (13)", "fire3": "Wildfire, 3 edges + PSPS (14)",
              "flood100": "Flood, 100-yr (15)", "flood500": "Flood, 500-yr (16)",
              "quake": "Earthquake (18)", "stall": "AV fleet stall (7)"}

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
    "font.family": "DejaVu Sans", "axes.titlelocation": "left",
})


def _rates():
    from grid_layer.feeder import Feeder
    from .scenarios import build_scenarios
    sc = build_scenarios(Feeder())
    return {k: (s.rate_per_yr, s.days, s.label, s.rows, s.basis) for k, s in sc.items()}


def _note(fig, text, y=0.01):
    fig.text(0.01, y, text, fontsize=8, color=MUTED, ha="left", va="bottom")


def _hgrid(ax):
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def _vgrid(ax):
    ax.xaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


# ============================================================ analysis
def paired(df, metric, cfg, ref, scen, variant="main"):
    a = df[(df.config == cfg) & (df.scenario == scen) & (df.variant == variant)].set_index("seed")[metric]
    b = df[(df.config == ref) & (df.scenario == scen) & (df.variant == variant)].set_index("seed")[metric]
    d = (a - b).dropna()
    return d.mean(), (d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else 0.0), len(d)


def annualize(df, metric, cfg, ref, rates, scens, variant="main"):
    """Annual-weighted mean of cfg and its paired difference vs ref, with a standard error."""
    m_ord = df[(df.config == cfg) & (df.scenario == "ordinary")][metric].mean()
    d_ord, se_ord, _ = paired(df, metric, cfg, ref, "ordinary")
    w_tot = sum(rates[s][0] * rates[s][1] for s in scens) / 365.0
    level, diff, var = m_ord, d_ord * (1 - w_tot), (se_ord * (1 - w_tot)) ** 2
    for s in scens:
        w = rates[s][0] * rates[s][1] / 365.0
        sub = df[(df.config == cfg) & (df.scenario == s) & (df.variant == variant)]
        if sub.empty:
            continue
        level += w * (sub[metric].mean() - m_ord)
        d, se, _ = paired(df, metric, cfg, ref, s, variant)
        diff += w * d
        var += (w * se) ** 2
    return level, diff, np.sqrt(var)


def placement_tables(df, rates):
    scens = [s for s in rates if s in set(df.scenario)]
    cfgs = ["base"] + [f"+{c}" for c in C.CANDIDATE_SITES]
    rows = []
    for cfg in cfgs:
        for scen in ["ordinary"] + scens:
            sub = df[(df.config == cfg) & (df.scenario == scen) & (df.variant == "main")]
            d, se, n = paired(df, "all_rider_wait", cfg, "base", scen)
            rows.append(dict(config=cfg, scenario=scen, n=len(sub),
                             rider_wait=sub.all_rider_wait.mean(), wait_served=sub.all_wait_served.mean(),
                             unserved_pct=sub.all_unserved_pct.mean(),
                             human_delay_per_trip=sub.human_delay_per_trip.mean(), mean_tti=sub.mean_tti.mean(),
                             depot_dark_h=sub.depot_dark_h.mean(), charge_queue_min=sub.charge_queue_min.mean(),
                             d_rider_wait=d, se_d_rider_wait=se))
    cond = pd.DataFrame(rows)
    ann = []
    for cfg in cfgs:
        lw, dw, sw = annualize(df, "all_rider_wait", cfg, "base", rates, scens)
        lu, du, su = annualize(df, "all_unserved_pct", cfg, "base", rates, scens)
        lh, dh, sh = annualize(df, "human_delay_per_trip", cfg, "base", rates, scens)
        haz = [s for s in scens if s not in ("rain",)]
        res = np.mean([paired(df, "all_rider_wait", cfg, "base", s)[0] for s in haz])
        ann.append(dict(config=cfg, site=NAMES.get(int(cfg[1:]), "") if cfg != "base" else "(none)",
                        annual_rider_wait=lw, d_annual_rider_wait=dw, se=sw,
                        annual_unserved_pct=lu, d_annual_unserved_pct=du,
                        annual_human_delay=lh, d_annual_human_delay=dh,
                        mean_d_wait_over_hazards=res))
    return cond, pd.DataFrame(ann)


def fleet_tables(df, rates):
    scens = [s for s in rates if s in set(df.scenario)]
    out = []
    for nt in sorted(df.tesla_n.unique()):
        ref = f"T{nt}:shared_existing"
        for cfg in sorted(df[df.tesla_n == nt].config.unique()):
            r = df[df.config == cfg].iloc[0]
            ns = "" if pd.isna(r["new_site"]) or r["new_site"] == "" else str(int(float(r["new_site"])))
            row = dict(tesla_n=nt, config=cfg, mode=r["mode"], new_site=ns)
            for co in ("all", "Waymo", "Tesla"):
                lv, d, se = annualize(df, f"{co}_rider_wait", cfg, ref, rates, scens)
                row[f"{co}_rider_wait"], row[f"d_{co}_rider_wait"], row[f"se_{co}"] = lv, d, se
            lv, d, _ = annualize(df, "all_unserved_pct", cfg, ref, rates, scens)
            row["all_unserved_pct"] = lv
            lv, d, _ = annualize(df, "human_delay_per_trip", cfg, ref, rates, scens)
            row["human_delay_per_trip"] = lv
            row["charge_queue_min_ord"] = df[(df.config == cfg) & (df.scenario == "ordinary")].charge_queue_min.mean()
            for s in ["ordinary"] + scens:
                row[f"{s}_rider_wait"] = df[(df.config == cfg) & (df.scenario == s)].all_rider_wait.mean()
            out.append(row)
    return pd.DataFrame(out)


# ============================================================ figures
def fig_architecture(path):
    fig, ax = plt.subplots(figsize=(11, 6.8))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 6.8)
    ax.axis("off")

    def box(x, y, w, h, title, body, edge):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    fc="white", ec=edge, lw=1.6))
        ax.text(x + 0.15, y + h - 0.2, title, fontsize=11, fontweight="bold", va="top", color=INK)
        ax.text(x + 0.15, y + h - 0.55, body, fontsize=8.6, va="top", color=INK2, linespacing=1.45)

    def arrow(p, q, label, lx, ly, color=INK2, rad=0.0, ha="center"):
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=14, lw=1.4, color=color,
                                     connectionstyle=f"arc3,rad={rad}"))
        ax.text(lx, ly, label, fontsize=8.3, color=INK, ha=ha, va="center",
                bbox=dict(fc=SURF, ec="none", pad=1.5))

    box(2.9, 4.75, 5.2, 1.4, "HAZARD LAYER  (scenarios.py)",
        "Failure Mode Table rows. Frequent rows sampled every minute\n"
        "(1-6, 7b, 8); rare rows simulated given they happen and\n"
        "weighted by annual rate (1b, 7, 9-18)", MUTED)
    box(0.2, 1.9, 4.2, 2.35, "GRID LAYER  (grid/grid_layer)",
        "IEEE 33-bus feeder, Baran & Wu 1989\n"
        "outage -> topology -> tie switching ->\n"
        "AC power flow -> depot curtailment\n\n"
        "every road node mapped to a bus\n(config.NODE_BUS)", BLUE)
    box(6.6, 1.9, 4.2, 2.35, "TRAFFIC LAYER  (traffic/v3 + sim.py)",
        "10 nodes, 17 edges, 1-min clock\n"
        "hourly human + AV demand (NHTS 2017)\n"
        "BPR congestion, re-routing every minute\n\n"
        "incidents, closures, rain", ORANGE)
    box(3.2, 0.15, 4.6, 1.25, "FLEETS + DEPOTS  (sim.py)",
        "Waymo / Tesla AVs: dispatch, range, charging, queues\n"
        "exclusive or universal depot access; 2 ports x 108 kW\n"
        "-> rider wait, unserved, congestion  (metrics)", AQUA)
    arrow((4.1, 4.75), (2.6, 4.27), "line / bus / substation\noutages (rows 9-12, 15-18)", 2.0, 4.62)
    arrow((6.9, 4.75), (8.4, 4.27), "edge closures,\ncapacity cuts", 9.1, 4.62)
    arrow((4.42, 3.3), (6.58, 3.3), "dark bus ->\ndark signals ->\ncapacity x0.40 art\nx0.85 fwy", 5.5, 3.85)
    arrow((4.42, 2.2), (6.58, 2.2), ">= 3 dark nodes\n-> fleet stall\n(row 7)", 5.5, 2.62)
    arrow((2.3, 1.9), (3.4, 1.15), "deliverable MW per depot\n0 = dark, partial = slower charging", 1.7, 1.45, color=BLUE)
    arrow((8.7, 1.9), (7.6, 1.15), "travel times,\nroutes", 9.05, 1.45, color=ORANGE)
    ax.text(0.2, 6.75, "How the layers are coupled", fontsize=14, fontweight="bold", va="top")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_network(path):
    from av_traffic_sim_tod import COORDS, EDGES
    fig, ax = plt.subplots(figsize=(9.5, 6.6))
    xy = {n: (lon, lat) for n, (lat, lon) in COORDS.items()}
    wui_nodes, flood_nodes = {1, 9, 10}, {5, 7}
    for n in wui_nodes:
        ax.scatter(*xy[n], s=2600, color=ORANGE, alpha=0.10, lw=0, zorder=1)
    for n in flood_nodes:
        ax.scatter(*xy[n], s=2600, color=BLUE, alpha=0.10, lw=0, zorder=1)
    wui_e = {tuple(sorted(e)) for e in C.WUI_EDGES}
    fl_e = {tuple(sorted(e)) for e in C.FLOOD500_EDGES}
    for u, v, cls in EDGES:
        (x1, y1), (x2, y2) = xy[u], xy[v]
        e = tuple(sorted((u, v)))
        col = ORANGE if e in wui_e else BLUE if e in fl_e else "#9a9994"
        ax.plot([x1, x2], [y1, y2], color=col, lw=3.2 if cls == "fwy" else 1.4,
                solid_capstyle="round", zorder=2, alpha=0.9)
    off = {3: (-0.012, 0.0075, "right"), 9: (0.012, 0.0075, "left"), 10: (-0.01, 0.0075, "center")}
    for n, (x, y) in xy.items():
        if n in C.EXISTING_DEPOTS:
            ax.scatter(x, y, s=170, marker="s", color=INK, edgecolor=SURF, lw=2, zorder=4)
        else:
            ax.scatter(x, y, s=170, marker="o", color=SURF, edgecolor=INK, lw=2, zorder=4)
        dy = 0.0075
        ox, oy, ha = off.get(n, (0.0, dy, "center"))
        ax.text(x + ox, y + oy, f"{n} {NAMES[n]}", ha=ha, va="bottom", fontsize=9, color=INK, zorder=5,
                bbox=dict(fc=SURF, ec="none", pad=0.6, alpha=0.85))
        ax.text(x, y - dy, f"bus {C.NODE_BUS[n]}", ha="center", va="top", fontsize=7.5, color=MUTED, zorder=5)
    ax.set_aspect(1.2)
    ax.margins(0.09)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    h = [plt.Line2D([], [], marker="s", ls="", color=INK, ms=9, label="Existing depot (Waymo's 4)"),
         plt.Line2D([], [], marker="o", ls="", mfc=SURF, mec=INK, mew=2, ms=9, label="Candidate site"),
         plt.Line2D([], [], color="#9a9994", lw=3.2, label="Freeway edge"),
         plt.Line2D([], [], color="#9a9994", lw=1.4, label="Arterial edge"),
         plt.Line2D([], [], color=ORANGE, lw=3, label="WUI edge / WUI feeder zone"),
         plt.Line2D([], [], color=BLUE, lw=3, label="Floodplain edge / zone")]
    ax.legend(handles=h, loc="lower right", frameon=False, fontsize=8.5)
    ax.set_title("10-node network, depots and hazard zones")
    _note(fig, "Bus = IEEE 33-bus feeder bus that powers that node's depot and traffic signals (placeholder geography).")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_placement_heatmap(cond, rates, path):
    scen = ["ordinary"] + [s for s in rates if s in set(cond.scenario)]
    cfgs = [f"+{c}" for c in C.CANDIDATE_SITES]
    M = np.array([[cond[(cond.config == c) & (cond.scenario == s)].d_rider_wait.iloc[0] for c in cfgs]
                  for s in scen])
    base = [cond[(cond.config == "base") & (cond.scenario == s)].rider_wait.iloc[0] for s in scen]
    lim = np.nanmax(np.abs(M))
    fig, ax = plt.subplots(figsize=(10, 6.4))
    im = ax.imshow(M, cmap=DIVERGING, vmin=-lim, vmax=lim, aspect="auto")
    for i in range(len(scen)):
        for j in range(len(cfgs)):
            v = M[i, j]
            ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=8.5,
                    color="white" if abs(v) > 0.6 * lim else INK)
    ax.set_xticks(range(len(cfgs)), [f"+{NAMES[int(c[1:])]}" for c in cfgs], rotation=0, fontsize=9)
    ax.set_yticks(range(len(scen)), [f"{SCEN_LABEL[s]}   [{b:.1f}]" for s, b in zip(scen, base)], fontsize=9)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks(np.arange(-.5, len(cfgs)), minor=True)
    ax.set_yticks(np.arange(-.5, len(scen)), minor=True)
    ax.grid(which="minor", color=SURF, lw=2)
    cb = fig.colorbar(im, ax=ax, shrink=0.75, pad=0.02)
    cb.set_label("change in mean rider wait vs. existing 4 depots (min)", color=INK2)
    cb.outline.set_visible(False)
    ax.set_title("Adding a 5th depot: change in rider wait, scenario by scenario")
    _note(fig, "Blue = shorter waits. [ ] = mean rider wait with only the existing 4 depots (min). Rider wait counts a "
          f"cancelled request at the 20-min cutoff.\nPaired by seed (common random numbers); "
          f"{int(cond[cond.scenario == 'ordinary'].n.max())} ordinary days, "
          f"{int(cond[cond.scenario != 'ordinary'].n.max())} days per hazard scenario.", y=-0.04)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_placement_ranking(ann, path):
    from matplotlib.ticker import MaxNLocator
    a = ann[ann.config != "base"].sort_values("d_annual_rider_wait")
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), gridspec_kw=dict(wspace=0.5))
    best = a.config.iloc[0]
    for ax, col, se, scale, title, unit, fmt in (
            (axes[0], "d_annual_rider_wait", "se", 1.0, "Rider wait, annual-weighted", "min per request", "{:+.2f}"),
            (axes[1], "d_annual_human_delay", None, 60.0, "Human-driver delay, annual-weighted",
             "seconds per trip", "{:+.1f}")):
        y = np.arange(len(a))
        vals = a[col].values * scale
        err = 1.96 * a[se].values * scale if se else np.zeros(len(a))
        colors = [BLUE if c == best else "#a9c8ee" for c in a.config]
        ax.barh(y, vals, height=0.55, color=colors, xerr=(err if se else None),
                error_kw=dict(ecolor=INK2, lw=1, capsize=3))
        ax.axvline(0, color=INK2, lw=1)
        ax.set_yticks(y, [f"+{s}" for s in a.site])
        ax.invert_yaxis()
        lo = min((vals - err).min(), 0)
        span = max(abs(lo), (vals + err).max(), 1e-6)
        ax.set_xlim(lo - 0.35 * span, max((vals + err).max(), 0) + 0.08 * span)
        for yi, v, e in zip(y, vals, err):
            ax.text(min(v - e, 0) - 0.03 * span, yi, fmt.format(v), va="center", ha="right", fontsize=8.5, color=INK)
        ax.xaxis.set_major_locator(MaxNLocator(5))
        _vgrid(ax)
        ax.set_xlabel(f"change vs. existing 4 depots ({unit})")
        ax.set_title(title, fontsize=11)
    fig.suptitle("Which 5th depot helps most over a year?", x=0.01, ha="left", fontsize=13, fontweight="bold",
                 y=1.03)
    _note(fig, "Annual weight: 365 ordinary days + each hazard scenario x annual rate x days of impact. "
          "Bars left of 0 are improvements. Whiskers: 95% CI of the paired difference.", y=-0.06)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_signals(df, path):
    sub = df[df.variant.isin(["signals_on", "signals_off"])]
    scen = [s for s in ["line_fault", "planned", "med", "psps", "fire3", "flood100", "flood500", "quake"]
            if s in set(sub.scenario)]
    on = [sub[(sub.variant == "signals_on") & (sub.scenario == s)].human_delay_per_trip.mean() for s in scen]
    off = [sub[(sub.variant == "signals_off") & (sub.scenario == s)].human_delay_per_trip.mean() for s in scen]
    dk = [sub[(sub.variant == "signals_on") & (sub.scenario == s)].dark_signal_node_h.mean() for s in scen]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    x = np.arange(len(scen))
    ax.bar(x - 0.15, off, width=0.28, color="#a9c8ee", label="signals ignored (layers uncoupled)")
    ax.bar(x + 0.15, on, width=0.28, color=ORANGE, label="dark signals -> all-way stops (coupled)")
    for xi, a_, b_, d in zip(x, off, on, dk):
        ax.text(xi + 0.15, b_ + 0.08, f"+{100 * (b_ / a_ - 1):.0f}%", ha="center", fontsize=8.5, color=INK)
    short = {"line_fault": "Line fault\n(9)", "planned": "Planned\n(11)", "med": "Major event\nday (10)",
             "psps": "PSPS\n(12)", "fire3": "Wildfire 3 edges\n+ PSPS (14)", "flood100": "Flood 100-yr\n(15)",
             "flood500": "Flood 500-yr\n(16)", "quake": "Earthquake\n(18)"}
    ax.set_xticks(x, [f"{short[s]}\n{d:.0f} node-h dark" for s, d in zip(scen, dk)], fontsize=8.3)
    ax.set_ylabel("human-driver delay (min per trip)")
    ax.set_ylim(0, max(on) * 1.15)
    _hgrid(ax)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Grid outages now cause congestion: dark traffic signals")
    _note(fig, f"Existing 4 depots; same seeds in both bars ({sub.seed.nunique()} days each). Row-7 fleet stall switched off here to "
          "isolate the signal effect.", y=-0.05)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_timeseries(path):
    rows = json.load(open(os.path.join(RES, "showcase_hourly.json")))
    for scen, title in (("med", "Major event day"), ("psps", "PSPS in the WUI zone")):
        fig, axes = plt.subplots(3, 1, figsize=(10, 8.2), sharex=True, gridspec_kw=dict(hspace=0.35))
        get = lambda cfg, var: next(r for r in rows if r["scenario"] == scen and r["config"] == cfg
                                    and r["variant"] == var)["_hourly"]
        h = np.arange(24)
        base_on, base_off = get("base", "signals_on"), get("base", "signals_off")
        ax = axes[0]
        ax.plot(h, [x["depot_power_frac"] * 100 for x in base_on], color=BLUE, lw=2, label="power available at the existing 4 depots")
        ax.plot(h, [x["dark_signal_nodes"] * 10 for x in base_on], color=ORANGE, lw=2,
                label="share of the 10 nodes with dark signals")
        ax.set_ylabel("%")
        ax.set_ylim(-5, 105)
        _hgrid(ax)
        ax.legend(frameon=False, fontsize=8.5, loc="lower right", bbox_to_anchor=(1, 1.0), ncol=2)
        ax.set_title("Grid state", fontsize=10.5)
        ax = axes[1]
        ax.plot(h, [x["mean_tti"] or np.nan for x in base_off], color="#a9c8ee", lw=2, label="signals ignored")
        ax.plot(h, [x["mean_tti"] or np.nan for x in base_on], color=ORANGE, lw=2, label="dark signals coupled")
        ax.set_ylabel("travel-time index")
        _hgrid(ax)
        ax.legend(frameon=False, fontsize=8.5, loc="upper left")
        ax.set_title("Congestion (mean over edges entered that hour)", fontsize=10.5)
        ax = axes[2]
        for cfg, col, lab in (("base", INK2, "existing 4"), ("+6", BLUE, "+ Downtown LA"),
                              ("+10", AQUA, "+ Pasadena")):
            s = get(cfg, "signals_on")
            ax.plot(h, [x["av_wait"] if x["av_wait"] is not None else np.nan for x in s], color=col, lw=2, label=lab)
        ax.set_ylabel("AV wait (min, served)")
        ax.set_xlabel("hour of day")
        ax.set_xticks(range(0, 24, 3), [f"{x:02d}:00" for x in range(0, 24, 3)])
        _hgrid(ax)
        ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=3)
        ax.set_title("Rider wait by request hour", fontsize=10.5)
        fig.suptitle(f"One simulated day: {title}", x=0.01, ha="left", fontsize=13, fontweight="bold", y=0.97)
        extra = ("  The Pasadena line lies on top of 'existing 4': Pasadena is in the WUI zone, so its depot is dark "
                 "for the whole PSPS." if scen == "psps" else "")
        _note(fig, "Single seed, for illustration; averages are in the other figures. Row-7 stall off." + extra, y=0.0)
        fig.savefig(path.replace(".png", f"_{scen}.png"), dpi=180, bbox_inches="tight")
        plt.close(fig)


def fig_fleets(ft, path):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), sharey=False, gridspec_kw=dict(wspace=0.35))
    sizes = sorted(ft.tesla_n.unique())
    x = np.arange(len(sizes))
    w = 0.26
    for ax, co, title in ((axes[0], "all", "All riders"), (axes[1], "Waymo", "Waymo riders"),
                          (axes[2], "Tesla", "Tesla riders")):
        vals = {}
        for k, (mode, lab, col) in enumerate((("shared", "Tesla shares Waymo's 4 (no new depot)", "#9a9994"),
                                              ("exclusive", "exclusive: Tesla's own new depot", ORANGE),
                                              ("universal", "universal: every depot open to both", BLUE))):
            ys, labs = [], []
            for nt in sizes:
                sub = ft[ft.tesla_n == nt]
                if mode == "shared":
                    r = sub[sub.config.str.endswith("shared_existing")].iloc[0]
                else:
                    r = sub[sub["mode"] == mode].sort_values("all_rider_wait").iloc[0]
                ys.append(r[f"{co}_rider_wait"])
                labs.append(NAMES[int(r.new_site)][:9] if mode != "shared" else "")
            vals[mode] = ys
            ax.bar(x + (k - 1) * w, ys, width=w - 0.03, color=col, label=lab)
            for xi, yv, lb in zip(x + (k - 1) * w, ys, labs):
                ax.text(xi, yv + 0.08, f"{yv:.1f}", ha="center", fontsize=7.5, color=INK)
                if lb:
                    ax.text(xi, 0.25, lb, ha="center", va="bottom", rotation=90, fontsize=7, color="white")
        ax.set_xticks(x, [f"Tesla {n} AVs\n({n / C.WAYMO['n_av']:.2g}x Waymo)" for n in sizes], fontsize=8.5)
        ax.set_title(title, fontsize=11)
        _hgrid(ax)
        ax.set_ylabel("rider wait, annual-weighted (min)")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, -0.2), ncol=3)
    fig.suptitle("A second fleet arrives: universal vs exclusive depots (best 5th site in each mode, named in bar)",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.03)
    _note(fig, "Waymo: 15 AVs on the existing 4 depots. Tesla demand scales with its fleet. Weighted over ordinary "
          "days, line faults, MED, PSPS, earthquake.", y=-0.2)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_fleet_sites(ft, path):
    nt = max(ft.tesla_n)
    sub = ft[ft.tesla_n == nt]
    sites = list(C.CANDIDATE_SITES)
    ex = [sub[(sub["mode"] == "exclusive") & (sub.new_site == str(s))].all_rider_wait.iloc[0] for s in sites]
    un = [sub[(sub["mode"] == "universal") & (sub.new_site == str(s))].all_rider_wait.iloc[0] for s in sites]
    sh = sub[sub.config.str.endswith("shared_existing")].all_rider_wait.iloc[0]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    x = np.arange(len(sites))
    ax.bar(x - 0.15, ex, width=0.28, color=ORANGE, label="exclusive (Tesla-only new depot)")
    ax.bar(x + 0.15, un, width=0.28, color=BLUE, label="universal (all 5 depots shared)")
    ax.axhline(sh, color=INK2, lw=1.2, ls="-", label=f"no new depot, Tesla shares Waymo's 4: {sh:.2f}")
    for xi, a_, b_ in zip(x, ex, un):
        ax.text(xi - 0.15, a_ + 0.05, f"{a_:.2f}", ha="center", fontsize=7.5)
        ax.text(xi + 0.15, b_ + 0.05, f"{b_:.2f}", ha="center", fontsize=7.5)
    ax.set_xticks(x, [NAMES[s] for s in sites])
    ax.set_ylabel("rider wait, all riders (min)")
    lo = min(min(ex), min(un), sh)
    ax.set_ylim(lo * 0.8, max(max(ex), max(un), sh) * 1.12)
    _hgrid(ax)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title(f"Where Tesla's depot goes, {nt}-AV Tesla fleet (equal to Waymo's)")
    _note(fig, "Annual-weighted; y-axis does not start at 0.", y=-0.03)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def fig_av_check(path):
    d = np.genfromtxt(os.path.join(RES, "av_demand_check_hourly.csv"), delimiter=",", names=True)
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.plot(d["hour"], 100 * d["nhts_human_share"], color=ORANGE, lw=2, label="human drivers, LA (NHTS 2017)")
    ax.plot(d["hour"], 100 * d["nhts_av_share"], color=BLUE, lw=2, label="taxi + Uber/Lyft, US (NHTS 2017) = AV profile")
    ax.scatter(d["hour"], 100 * d["simulated_av_share"], s=28, color=BLUE, edgecolor=SURF, lw=1.5, zorder=3,
               label="AV requests the simulator generated (300 days)")
    ax.set_xticks(range(0, 24, 3), [f"{x:02d}:00" for x in range(0, 24, 3)])
    ax.set_ylabel("% of the day's trips")
    ax.set_ylim(0, 13)
    _hgrid(ax)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=2)
    ax.set_title("AV demand = ride-hail shape, scaled to 5% of VMT")
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


# ============================================================ markdown
def md_table(df, cols, fmt):
    head = "| " + " | ".join(c for c, _ in cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    body = ""
    for _, r in df.iterrows():
        body += "| " + " | ".join(fmt.get(k, "{}").format(r[k]) for _, k in cols) + " |\n"
    return head + body


def main():
    os.makedirs(FIG, exist_ok=True)
    rates = _rates()
    md = ["# Coupled simulation results\n"]
    fig_architecture(os.path.join(FIG, "fig1_architecture.png"))
    fig_coverage(os.path.join(FIG, "fig0_coverage.png"))
    fig_network(os.path.join(FIG, "fig2_network.png"))
    gp = os.path.join(RES, "grid_n1_sites.csv")
    fig_grid_n1(pd.read_csv(gp) if os.path.exists(gp) else grid_n1_sites(), os.path.join(FIG, "fig10_grid_n1_sites.png"))
    if os.path.exists(os.path.join(RES, "av_demand_check_hourly.csv")):
        fig_av_check(os.path.join(FIG, "fig9_av_demand_check.png"))
    md.append("## Scenario rates used for annual weighting\n")
    md.append("| Scenario | Rows | Events / yr | Days per event | Basis |\n|---|---|---|---|---|")
    for k, (r, d, lab, rows, basis) in rates.items():
        md.append(f"| {lab} | {rows} | {r:.4g} | {d:g} | {basis} |")
    p = os.path.join(RES, "placement_runs.csv")
    if os.path.exists(p):
        df = pd.read_csv(p)
        cond, ann = placement_tables(df, rates)
        cond.to_csv(os.path.join(RES, "placement_by_scenario.csv"), index=False)
        ann.to_csv(os.path.join(RES, "placement_annual.csv"), index=False)
        fig_placement_heatmap(cond, rates, os.path.join(FIG, "fig3_placement_heatmap.png"))
        fig_placement_ranking(ann, os.path.join(FIG, "fig4_placement_ranking.png"))
        fig_signals(df, os.path.join(FIG, "fig5_dark_signals.png"))
        md.append("\n## Placement (Waymo, 15 AVs, existing depots 1, 2, 4, 5 + one candidate)\n")
        md.append(md_table(ann.sort_values("d_annual_rider_wait"),
                           [("Config", "config"), ("Site", "site"), ("Rider wait (min)", "annual_rider_wait"),
                            ("Δ wait vs base", "d_annual_rider_wait"), ("SE", "se"),
                            ("Unserved %", "annual_unserved_pct"), ("Human delay (min/trip)", "annual_human_delay"),
                            ("Δ human delay", "d_annual_human_delay"),
                            ("Mean Δ wait over hazard scenarios", "mean_d_wait_over_hazards")],
                           {k: "{:.3f}" for k in ("annual_rider_wait", "d_annual_rider_wait", "se",
                                                  "annual_unserved_pct", "annual_human_delay",
                                                  "d_annual_human_delay", "mean_d_wait_over_hazards")}))
        # stall-trigger sensitivity
        sens = []
        for cfg in ann.config:
            for s in ["med", "psps", "fire3", "flood500", "quake"]:
                a = df[(df.config == cfg) & (df.scenario == s) & (df.variant == "no_row7_trigger")]
                b = df[(df.config == cfg) & (df.scenario == s) & (df.variant == "main")]
                if len(a):
                    sens.append(dict(config=cfg, scenario=s, wait_trigger_on=b.all_rider_wait.mean(),
                                     wait_trigger_off=a.all_rider_wait.mean(),
                                     d_vs_base_off=paired(df, "all_rider_wait", cfg, "base", s, "no_row7_trigger")[0]))
        pd.DataFrame(sens).to_csv(os.path.join(RES, "placement_row7_sensitivity.csv"), index=False)
    if os.path.exists(os.path.join(RES, "showcase_hourly.json")):
        fig_timeseries(os.path.join(FIG, "fig6_timeseries.png"))
    p = os.path.join(RES, "fleets_runs.csv")
    if os.path.exists(p):
        df = pd.read_csv(p)
        ft = fleet_tables(df, rates)
        ft.to_csv(os.path.join(RES, "fleets_summary.csv"), index=False)
        fig_fleets(ft, os.path.join(FIG, "fig7_fleets_universal_vs_exclusive.png"))
        fig_fleet_sites(ft, os.path.join(FIG, "fig8_tesla_site.png"))
        md.append("\n## Multi-fleet (Waymo 15 AVs + Tesla), annual-weighted rider wait (min)\n")
        md.append(md_table(ft.sort_values(["tesla_n", "all_rider_wait"]),
                           [("Tesla AVs", "tesla_n"), ("Config", "config"), ("All", "all_rider_wait"),
                            ("Waymo", "Waymo_rider_wait"), ("Tesla", "Tesla_rider_wait"),
                            ("Unserved %", "all_unserved_pct"), ("Human delay", "human_delay_per_trip"),
                            ("Charge queue (min/day, ordinary)", "charge_queue_min_ord")],
                           {k: "{:.3f}" for k in ("all_rider_wait", "Waymo_rider_wait", "Tesla_rider_wait",
                                                  "all_unserved_pct", "human_delay_per_trip")} |
                           {"charge_queue_min_ord": "{:.1f}"}))
    if all(os.path.exists(os.path.join(RES, f)) for f in ("placement_runs.csv", "fleets_runs.csv",
                                                           "placement_3p5mpk_runs.csv", "fleets_3p5mpk_runs.csv")):
        out = energy_compare(rates)
        fig_energy(out, os.path.join(FIG, "fig11_energy_compare.png"))
        md.append("\n## Energy use: 2.0 mi/kWh (main) vs 3.5 mi/kWh (earlier value)\n")
        md.append("| Config | Rider wait at 3.5 | Δ vs existing 4 | Rider wait at 2.0 | Δ vs existing 4 |\n|---|---|---|---|---|")
        a35, a20 = out["3.5"][0].set_index("config"), out["2.0"][0].set_index("config")
        for cfg in a20.index:
            md.append(f"| {cfg} | {a35.loc[cfg, 'annual_rider_wait']:.3f} | {a35.loc[cfg, 'd_annual_rider_wait']:+.3f} | "
                      f"{a20.loc[cfg, 'annual_rider_wait']:.3f} | {a20.loc[cfg, 'd_annual_rider_wait']:+.3f} |")
    with open(os.path.join(RES, "summary.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print("wrote results/summary.md and figures/")



# ============================================================ grid-only siting study
def grid_n1_sites(ports_list=(2, 4, 6)):
    """Every single-line outage (N-1) with the existing 4 depots + one candidate at a given size:
    how often is the candidate depot fully available, partially available (curtailed) or dark?
    Each outage is weighted by its share of routine failures (equal rate per line)."""
    from grid_layer.feeder import Feeder
    f = Feeder()
    rows = []
    for ports in ports_list:
        mw = ports * C.PORT_MW
        for c in C.CANDIDATE_SITES:
            built = set(C.EXISTING_DEPOTS) | {c}
            dem = {f"N{n}": (mw if n in built else 0.0) for n in C.NODE_BUS}
            full = part = dark = 0
            fr_sum = 0.0
            for ln in sorted(f.normal_lines):
                s = f.solve(lines_down={ln}, depot_demand=dem)
                x = s.depots[f"N{c}"]["deliverable_mw"] / mw
                fr_sum += x
                if x >= 0.999:
                    full += 1
                elif x <= 1e-6:
                    dark += 1
                else:
                    part += 1
            intact = f.solve(depot_demand=dem).depots[f"N{c}"]["deliverable_mw"] / mw
            n = len(f.normal_lines)
            rows.append(dict(ports=ports, depot_mw=mw, site=c, name=NAMES[c], bus=C.NODE_BUS[c],
                             intact_frac=intact, full=full / n, partial=part / n, dark=dark / n,
                             mean_frac=fr_sum / n))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "grid_n1_sites.csv"), index=False)
    return df


def fig_grid_n1(df, path):
    sizes = sorted(df.ports.unique())
    fig, axes = plt.subplots(1, len(sizes), figsize=(13.5, 4.2), sharey=True, gridspec_kw=dict(wspace=0.32))
    for ax, p in zip(axes, sizes):
        sub = df[df.ports == p].set_index("site").loc[list(C.CANDIDATE_SITES)]
        y = np.arange(len(sub))
        left = np.zeros(len(sub))
        for col, colr, lab in (("full", BLUE, "full power"), ("partial", YELLOW, "partial (curtailed)"),
                               ("dark", ORANGE, "dark")):
            v = sub[col].values * 100
            ax.barh(y, v, left=left, height=0.55, color=colr, label=lab, edgecolor=SURF, lw=2)
            left += v
        for yi, it in zip(y, sub.intact_frac.values):
            if it < 0.999:
                ax.text(101, yi, f"intact: {100 * it:.0f}%", va="center", fontsize=7.5, color=INK2)
        ax.set_yticks(y, [f"{NAMES[s]} (bus {C.NODE_BUS[s]})" for s in sub.index])
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel("% of single-line outages")
        ax.set_title(f"{p} ports = {p * C.PORT_MW:.2f} MW", fontsize=10.5)
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left", bbox_to_anchor=(0, -0.18), ncol=3)
    fig.suptitle("Grid side of siting: the 5th depot's power under every single-line outage (N-1)",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold", y=1.04)
    _note(fig, "Existing 4 depots at the same size. Tie switching restores customers first; depots on borrowed "
          "capacity are curtailed first. 'intact' = power available with nothing failed.", y=-0.2)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)



# ============================================================ coverage table (same look as the 11/13 deck)
def fig_coverage(path):
    from matplotlib.patches import FancyBboxPatch as FB
    rows = [("1", "Human incident, reduced capacity", "v3", "In v3"),
            ("1b", "Rain day", "v3", "In v3"),
            ("1c", "Recurring congestion", "v3", "In v3"),
            ("2", "Human incident, edge closed", "v3", "In v3"),
            ("3", "Human major incident, ≥3 edges", "no", "Added"),
            ("4", "AV incident, reduced capacity", "v3", "In v3"),
            ("5", "AV incident, edge closed", "v3", "In v3"),
            ("6", "AV major incident, ≥3 edges", "no", "Added"),
            ("7", "AV connectivity loss, fleet stalls", "no", "Added"),
            ("7b", "AV battery depletion", "part", "Added"),
            ("8", "AV obstructs emergency response", "no", "Added"),
            ("9", "Depot outage, unplanned", "v3", "Grid layer"),
            ("10", "Depot outage, major event day", "part", "Grid layer"),
            ("11", "Depot outage, planned", "part", "Grid layer"),
            ("12", "PSPS, ≥3 depots", "part", "Grid layer"),
            ("13", "Wildfire, ≥1 edge closed ≥24 h", "no", "Scenario"),
            ("14", "Wildfire, ≥3 edges", "no", "Scenario"),
            ("15", "Flood, floodplain edge", "no", "Scenario"),
            ("16", "Flood, 500-yr, ≥3 edges", "no", "Scenario"),
            ("18", "Earthquake M≥6.7, ≥3 edges", "no", "Scenario")]
    GREEN, RED, AMBER = "#3daa2e", "#d9534f", "#f0b400"
    old = {"v3": (GREEN, "✓ In v3", "white"), "no": (RED, "× Not yet", "white"), "part": (AMBER, "◐ Partial", INK)}
    fig, ax = plt.subplots(figsize=(10, 5.625))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.625)
    ax.axis("off")
    top, rh = 5.0, 0.232
    ax.text(1.0, 5.38, "Failure Mode Table coverage: 11/13 vs now (coupled model)", fontsize=12.5,
            fontweight="bold", va="center", color=INK)
    for x, lab in ((1.05, "Row"), (1.7, "Hazard"), (5.95, "11/13"), (7.45, "Now")):
        ax.text(x, top + 0.12, lab, fontsize=9, fontweight="bold", color=INK2, va="center")
    for i, (r, h, o, n) in enumerate(rows):
        y = top - (i + 0.5) * rh
        if i % 2 == 0:
            ax.add_patch(plt.Rectangle((1.0, y - rh / 2), 7.9, rh, color="#f4f4f2", lw=0))
        ax.text(1.05, y, r, fontsize=9, fontweight="bold", va="center", color=INK)
        ax.text(1.7, y, h, fontsize=9, va="center", color=INK)
        for x, (col, lab, tc) in ((5.95, old[o]), (7.45, (GREEN, "✓ " + n, "white"))):
            ax.add_patch(FB((x, y - rh * 0.36), 1.25, rh * 0.72, boxstyle="round,pad=0,rounding_size=0.05",
                            fc=col, ec="none"))
            ax.text(x + 0.625, y, lab, fontsize=8.2, fontweight="bold", ha="center", va="center", color=tc)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)



# ============================================================ energy-use comparison (3.5 vs 2.0 mi/kWh)
def energy_compare(rates):
    """Annual tables at 3.5 mi/kWh (results/*_3p5mpk_runs.csv) next to the main 2.0 runs."""
    out = {}
    for tag, pf, ff in (("2.0", "placement_runs.csv", "fleets_runs.csv"),
                        ("3.5", "placement_3p5mpk_runs.csv", "fleets_3p5mpk_runs.csv")):
        pdf, fdf = pd.read_csv(os.path.join(RES, pf)), pd.read_csv(os.path.join(RES, ff))
        _, ann = placement_tables(pdf, rates)
        out[tag] = (ann, fleet_tables(fdf, rates),
                    pdf[(pdf.config == "base") & (pdf.scenario == "ordinary")].charge_queue_min.mean())
    rows = []
    for tag, (ann, ft, q) in out.items():
        for _, r in ann.iterrows():
            rows.append(dict(mi_per_kwh=tag, kind="placement", config=r.config, rider_wait=r.annual_rider_wait,
                             d_vs_ref=r.d_annual_rider_wait, se=r.se))
        for _, r in ft.iterrows():
            rows.append(dict(mi_per_kwh=tag, kind="fleets", config=r.config, rider_wait=r.all_rider_wait,
                             d_vs_ref=r.d_all_rider_wait, se=r.se_all))
        rows.append(dict(mi_per_kwh=tag, kind="queue_min_per_day_base_ordinary", config="base", rider_wait=q))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(RES, "energy_compare.csv"), index=False)
    return out


def fig_energy(out, path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), gridspec_kw=dict(wspace=0.35, width_ratios=[1.15, 1]))
    sites = list(C.CANDIDATE_SITES)
    ax = axes[0]
    x = np.arange(len(sites))
    for k, (tag, col, lab) in enumerate((("3.5", "#a9c8ee", "3.5 mi/kWh (11/13 value)"),
                                         ("2.0", BLUE, "2.0 mi/kWh (Waymo I-Pace estimate)"))):
        ann = out[tag][0].set_index("config")
        v = [ann.loc[f"+{s}", "d_annual_rider_wait"] for s in sites]
        e = [1.96 * ann.loc[f"+{s}", "se"] for s in sites]
        ax.bar(x + (k - 0.5) * 0.36, v, width=0.34, color=col, label=lab, yerr=e,
               error_kw=dict(ecolor=INK2, lw=0.8, capsize=2))
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xticks(x, [NAMES[s].replace(" ", "\n", 1) if len(NAMES[s]) > 10 else NAMES[s] for s in sites], fontsize=8.5)
    ax.set_ylabel("change in rider wait vs existing 4 (min)")
    ax.set_title("5th depot: annual change in rider wait", fontsize=11)
    _hgrid(ax)
    ax.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    ax = axes[1]
    sizes = sorted(out["2.0"][1].tesla_n.unique())
    x = np.arange(len(sizes))
    for k, (tag, col) in enumerate((("3.5", "#a9c8ee"), ("2.0", BLUE))):
        ft = out[tag][1]
        gain = []
        for nt in sizes:
            sub = ft[ft.tesla_n == nt]
            ex = sub[sub["mode"] == "exclusive"].all_rider_wait.min()
            un = sub[sub["mode"] == "universal"].all_rider_wait.min()
            gain.append(ex - un)
        ax.bar(x + (k - 0.5) * 0.36, gain, width=0.34, color=col)
        for xi, g in zip(x + (k - 0.5) * 0.36, gain):
            ax.text(xi, g + 0.02, f"{g:.2f}", ha="center", fontsize=8.5)
    ax.set_xticks(x, [f"Tesla {n} AVs" for n in sizes])
    ax.set_ylabel("min saved, best universal vs best exclusive")
    ax.set_title("Gain from universal depots", fontsize=11)
    _hgrid(ax)
    q35, q20 = out["3.5"][2], out["2.0"][2]
    fig.suptitle("Using 2.0 instead of 3.5 mi/kWh", x=0.01, ha="left", fontsize=13, fontweight="bold", y=1.03)
    _note(fig, f"Longer charging sessions (3.6 vs 6.3 mi of range per minute). Charging queue at the existing 4 depots on an "
          f"ordinary day: {q35:.0f} -> {q20:.0f} min/day. Whiskers: 95% CI.", y=-0.16)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
