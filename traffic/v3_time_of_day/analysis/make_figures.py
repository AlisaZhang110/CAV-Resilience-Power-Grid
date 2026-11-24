"""Rebuild every slide figure from results/ (run run_experiments.py and siting_check.py first)."""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import csv, json, math, itertools, statistics as st
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
from av_traffic_sim_tod import (NODES, EDGES, COORDS, EDGE_HAZARDS, NODE_HAZARDS, haversine_mi,
                                CIRCUITY, load_profiles)
from style import *
RES = HERE / "results"
(HERE / "figures").mkdir(exist_ok=True)

# ======================= static figures ======================= #
# ---------- 1. network map ----------
ROADS = {(1,2):"I-10",(2,5):"I-405",(5,4):"I-405",(5,7):"SR-90",(5,6):"I-10",(8,6):"I-10",(9,6):"US-101",
         (6,10):"SR-110",(9,10):"US-101/SR-134"}
fig, ax = plt.subplots(figsize=(13, 7.3))
ax.grid(False); [s_.set_visible(False) for s_ in ax.spines.values()]; ax.set_xticks([]); ax.set_yticks([])
xy = {1: (1.0, 9.6), 2: (3.6, 9.6), 3: (6.2, 9.6), 9: (8.8, 9.6), 10: (12.4, 9.0), 5: (3.9, 8.1),
      6: (8.4, 8.1), 4: (1.9, 7.45), 8: (5.9, 6.7), 7: (0.7, 5.6)}
LBL = {1: (0, 0.42, "center"), 2: (0, 0.42, "center"), 3: (0, 0.42, "center"), 9: (0, 0.42, "center"),
       10: (0, 0.42, "center"), 5: (-0.35, 0.33, "right"), 6: (0.4, -0.38, "left"), 4: (-0.35, 0, "right"),
       8: (0, -0.45, "center"), 7: (0, -0.45, "center")}
EOFF = {(1, 2): (0, 0.18), (2, 3): (0, 0.18), (3, 9): (0, 0.18), (9, 10): (0.3, 0.22), (1, 5): (0.25, 0.12),
        (1, 7): (-0.55, 0), (2, 5): (0.5, 0.05), (3, 5): (0.2, 0.22), (5, 6): (0.0, 0.15), (5, 4): (-0.15, 0.35),
        (5, 8): (0.55, 0.12), (5, 7): (0.45, -0.3), (4, 8): (-0.2, -0.27), (8, 9): (0.55, 0.25), (8, 6): (0.55, -0.15),
        (9, 6): (0.45, 0.0), (6, 10): (0.3, -0.25)}
for u, v, c in EDGES:
    (x1, y1), (x2, y2) = xy[u], xy[v]
    if c == "fwy":
        ax.plot([x1, x2], [y1, y2], color=BLUE, lw=5, solid_capstyle="round", zorder=2)
    else:
        ax.plot([x1, x2], [y1, y2], color=MUTED, lw=2.4, ls=(0, (4, 3)), zorder=1)
    mi = haversine_mi(COORDS[u], COORDS[v]) * CIRCUITY
    ffmin = max(1, round(mi / (45 if c == "fwy" else 25) * 60))
    ox, oy = EOFF.get((u, v), (0, 0))
    mx, my = (x1 + x2) / 2 + ox, (y1 + y2) / 2 + oy
    lab = (ROADS[(u, v)] + "\n" if c == "fwy" else "") + f"{mi:.1f} mi, {ffmin} min"
    ax.text(mx, my, lab, fontsize=9.5, color=BLUE if c == "fwy" else INK2, ha="center", va="center", zorder=4,
            fontweight="bold" if c == "fwy" else "normal",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
for n, (x, y) in xy.items():
    ax.scatter([x], [y], s=620, color="white", edgecolor=INK, linewidth=2.2, zorder=5)
    if n in (1, 2, 4, 5):
        ax.scatter([x], [y], s=1250, facecolor="none", edgecolor=ORANGE, linewidth=2.6, zorder=5)
    ax.text(x, y, str(n), ha="center", va="center", fontsize=12, fontweight="bold", zorder=6)
    dx, dy, ha = LBL[n]
    ax.text(x + dx, y + dy, NODES[n], fontsize=13.5, color=INK, ha=ha, va="center", zorder=6, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"))
handles = [Line2D([], [], color=BLUE, lw=5, label="Freeway edge (9): 45 mph free-flow, capacity 30 veh/h per direction"),
           Line2D([], [], color=MUTED, lw=2.4, ls=(0, (4, 3)), label="Arterial edge (8): 25 mph, capacity 12 veh/h per direction"),
           Line2D([], [], marker="o", ls="", ms=17, mfc="white", mec=INK, mew=2, label="Node = neighbourhood (sim default: a charger at every node)"),
           Line2D([], [], marker="o", ls="", ms=24, mfc="none", mec=ORANGE, mew=2.6, label="Charging stations in the notes, Nc = {1, 2, 4, 5}")]
ax.legend(handles=handles, loc="lower right", fontsize=11.5, bbox_to_anchor=(1.0, 0.0))
ax.set_title("Prototype road network: 10 nodes, 17 edges (Project #4 notes, p.5)", pad=10)
ax.set_xlim(-0.6, 13.6); ax.set_ylim(3.9, 10.3)
fig.text(0.01, 0.012, "Layout follows the hand-drawn sketch in the Project #4 notes (p.5). Distances = straight line between neighbourhood centres x 1.3; edge classes and speeds are modeling assumptions.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig01_network.png", dpi=200); plt.close(fig)

# ---------- 2. demand profiles ----------
prof = load_profiles()
hrs = list(range(24))
fig, axs = plt.subplots(1, 2, figsize=(13, 5.6), sharey=True)
for ax, dt in zip(axs, ("weekday", "weekend")):
    h = [100 * x for x in prof[f"human_trips_{dt}"]]
    a = [100 * x for x in prof[f"av_trips_{dt}"]]
    ax.plot(hrs, h, color=BLUE, lw=2.5, marker="o", ms=5)
    ax.plot(hrs, a, color=ORANGE, lw=2.5, marker="o", ms=5)
    ax.set_title(dt.capitalize())
    ax.set_xticks(range(0, 24, 6)); ax.set_xticklabels([f"{x:02d}:00" for x in range(0, 24, 6)])
    ax.set_xlim(-0.5, 23.5); ax.set_ylim(0, 12)
    ax.text(23.4, h[-1] + 0.5, "Human drivers", color=INK, ha="right", fontsize=13) if False else None
    if dt == "weekday":
        ax.annotate("AM peak 07:00\n9.1%", (7, h[7]), (0.3, 10.6), fontsize=11.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED))
        ax.annotate("PM peak 17:00\n9.1%", (17, h[17]), (18.6, 10.6), fontsize=11.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED))
        ax.annotate("Ride-hail stays\nhigh late night", (22, a[22]), (12.5, 0.8), fontsize=11.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED))
    else:
        ax.annotate("Ride-hail peak\n22:00, 8.7%", (22, a[22]), (17.0, 10.6), fontsize=11.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.set_xlabel("Trip start hour")
axs[0].set_ylabel("% of the day's trips")
fig.legend(handles=[Line2D([], [], color=BLUE, lw=2.5, marker="o", label="Human-driven trips (NHTS 2017, LA metro, n = 10,601 wkday)"),
                       Line2D([], [], color=ORANGE, lw=2.5, marker="o", label="AV proxy: taxi/ride-hail trips (NHTS 2017, US, n = 2,092 wkday)")],
              loc="lower center", fontsize=11.5, ncol=2, bbox_to_anchor=(0.5, 0.0))
fig.suptitle("Hourly demand profiles that drive the simulation", x=0.01, ha="left", fontweight="bold", fontsize=18)
fig.tight_layout(rect=(0, 0.07, 1, 1)); fig.savefig(OUT + "fig03_demand_profiles.png", dpi=200); plt.close(fig)

# ---------- 3. coverage matrix ----------
rows = [("1", "Human incident, reduced capacity", "in"), ("1b", "Rain day", "in"), ("1c", "Recurring congestion", "in"),
        ("2", "Human incident, edge closed", "in"), ("3", "Human major incident, ≥3 edges", "no"),
        ("4", "AV incident, reduced capacity", "in"), ("5", "AV incident, edge closed", "in"),
        ("6", "AV major incident, ≥3 edges", "no"), ("7", "AV connectivity loss, fleet stalls", "no"),
        ("7b", "AV battery depletion", "part"), ("8", "AV obstructs emergency response", "no"),
        ("9", "Depot outage, unplanned", "in"), ("10", "Depot outage, major event day", "part"),
        ("11", "Depot outage, planned", "part"), ("12", "PSPS, ≥3 depots", "part"),
        ("13", "Wildfire, ≥1 edge closed ≥24 h", "no"), ("14", "Wildfire, ≥3 edges", "no"),
        ("15", "Flood, floodplain edge", "no"), ("16", "Flood, 500-yr, ≥3 edges", "no"),
        ("18", "Earthquake M≥6.7, ≥3 edges", "no")]
feas = {"2": 1, "5": 2, "11": 3, "9": 4, "1c": 5, "1": 6, "4": 7, "13": 8, "15": 9, "1b": 10, "3": 11, "6": 12, "10": 13, "12": 14, "14": 15}
note = {"1": "stochastic, all edges", "1b": "--rain switch", "1c": "emerges from BPR + demand", "2": "stochastic, freeway edges",
        "4": "stochastic, all edges", "5": "stochastic, freeway edges", "7b": "output: stranded AVs", "9": "stochastic, per depot",
        "10": "per depot (independent)", "11": "forced --outage", "12": "forced multi-depot --outage",
        "3": "next: seed edge + 2 neighbours", "6": "same code as row 3", "13": "needs WUI edge tags", "15": "needs floodplain edge tag",
        "14": "multi-day horizon", "16": "multi-day horizon", "18": "multi-day; grid side exists", "7": "scenario: % of AVs stall", "8": "add to clearance time"}
ST = {"in": ("#0ca30c", "✓ In v3"), "part": ("#fab219", "◐ Partial"), "no": ("#d03b3b", "✗ Not yet")}
fig, ax = plt.subplots(figsize=(13, 7.4)); ax.axis("off")
ax.set_xlim(0, 13); ax.set_ylim(-0.6, len(rows) + 0.8)
hdr = [(0.1, "Row"), (0.9, "Hazard"), (6.1, "Status"), (7.9, "How"), (11.6, "Feasibility\nrank (col T)")]
for x, t in hdr:
    ax.text(x, len(rows) + 0.25, t, fontsize=12, fontweight="bold", color=INK2, va="center")
for i, (r, name, status) in enumerate(rows):
    y = len(rows) - 1 - i
    if i % 2 == 0:
        ax.add_patch(FancyBboxPatch((0, y - 0.45), 13, 0.9, boxstyle="square,pad=0", fc="#f6f6f3", ec="none"))
    col, lab = ST[status]
    ax.text(0.1, y, r, fontsize=12.5, fontweight="bold", va="center", color=INK)
    ax.text(0.9, y, name, fontsize=12.5, va="center", color=INK)
    ax.add_patch(FancyBboxPatch((6.05, y - 0.32), 1.6, 0.64, boxstyle="round,pad=0.02,rounding_size=0.15", fc=col, ec="none", alpha=0.9))
    ax.text(6.85, y, lab, fontsize=11.5, va="center", ha="center", color="#0b0b0b" if status == "part" else "white", fontweight="bold")
    ax.text(7.9, y, note.get(r, ""), fontsize=11.5, va="center", color=INK2)
    ax.text(12.2, y, str(feas.get(r, "–")), fontsize=12.5, va="center", ha="center", color=INK)
ax.set_title("Failure Mode Table coverage after v3 (traffic layer)", pad=4)
fig.tight_layout(); fig.savefig(OUT + "fig10_coverage.png", dpi=200); plt.close(fig)

# ---------- 4. grid hosting capacity ----------
bus, mw, bind = [], [], []
for r in csv.DictReader(open(HERE.parents[2] / "grid" / "outputs" / "hosting_capacity.csv")):
    bus.append(int(r["bus"])); mw.append(float(r["hosting_capacity_mw"])); bind.append(r["binding_constraint"])
fig, ax = plt.subplots(figsize=(13, 5.4))
cols = [BLUE if "overload" in b else ORANGE for b in bind]
ax.bar(bus, mw, color=cols, width=0.75, edgecolor="white", linewidth=1)
for b, lab in ((5, "Depot: mid-trunk\n0.9 MW"), (17, "Depot: feeder end\n0.1 MW"), (21, "Depot: strong lateral\n2.0 MW"), (32, "Depot: weak lateral\n0.3 MW")):
    v = mw[bus.index(b)]
    ax.annotate(lab, (b, v), (b, v + 0.55), ha="center", fontsize=11, color=INK, arrowprops=dict(arrowstyle="-", color=INK2))
ax.set_ylim(0, 3.2); ax.set_xlim(0.3, 32.7); ax.set_xticks([1, 5, 10, 15, 17, 18, 21, 25, 32])
ax.set_xlabel("Feeder bus (IEEE 33-bus, pandapower index)"); ax.set_ylabel("Hosting capacity (MW)")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=BLUE, label="Limited by line overload (substation exit)"),
                   plt.Rectangle((0, 0), 1, 1, color=ORANGE, label="Limited by undervoltage (< 0.95 p.u.)")], loc="upper center", bbox_to_anchor=(0.45, 1.0), fontsize=11.5)
ax.set_title("Grid layer: how much depot load each bus can host (one depot at a time)")
fig.text(0.01, 0.01, "Source: grid/outputs/hosting_capacity.csv (grid_layer studies). Line ratings are placeholders; voltage-limited values use the case's real impedances.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig11_grid_hosting.png", dpi=200); plt.close(fig)

# ---------- 5. coupling example ----------
hours = list(range(13, 24))
dem = [0.95, 0.95, 0.95, 1.425, 1.425, 1.425, 1.425, 1.425, 0.95, 0.95, 0.95]
dlv = [0.95, 0.95, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.95, 0.95, 0.95]
fig, ax = plt.subplots(figsize=(13, 5.2))
ax.step(hours, dem, where="post", color=INK2, lw=2.5, ls=(0, (5, 3)), label="Depot charging demand (placeholder fleet)")
ax.fill_between(hours, dlv, step="post", color=BLUE, alpha=0.25)
ax.step(hours, dlv, where="post", color=BLUE, lw=2.5, label="Power the grid can deliver to depots")
ax.axvspan(15, 21, color=RED, alpha=0.07)
ax.text(18, 1.62, "Feeder line 1–18 out 15:00–21:00 → tie switch closed → depots curtailed to 0.30 MW", ha="center", fontsize=12, color=INK)
ax.set_xticks(hours[:-1]); ax.set_xticklabels([f"{h}:00" for h in hours[:-1]]); ax.set_xlim(13, 23); ax.set_ylim(0, 1.8); ax.set_ylabel("MW (all depots)")
ax.legend(loc="lower left", fontsize=11.5)
ax.set_title("Next step, coupling: the grid layer already returns deliverable MW per hour")
fig.text(0.01, 0.01, "Source: grid/run_examples.py scenario 6 (demand comes from a placeholder transportation layer, not yet from the v3 fleet).", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig12_grid_coupling.png", dpi=200); plt.close(fig)


# ======================= experiment figures ======================= #
D = json.load(open(RES / "experiments.json"))
by = defaultdict(list)
for r in D: by[r["kind"]].append(r)
base = {r["seed"]: r for r in by["base"]}
NUM = {}

def ci(xs):
    m = st.mean(xs); s = st.stdev(xs) / math.sqrt(len(xs)); return m, 1.96 * s

# ---- F6 congestion by hour
hrs = range(24)
fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 6.8), sharex=True, gridspec_kw={"height_ratios": [1, 1.3]})
for dt, col in (("weekday", BLUE), ("weekend", ORANGE)):
    rs = [r for r in by["hourly"] if r["kw"].get("day_type") == dt]
    dep = [st.mean(r["hourly"][h]["human_departures"] for r in rs) for h in hrs]
    tti = [st.mean((r["hourly"][h]["mean_tti"] or 1.0) for r in rs) for h in hrs]
    a1.plot(hrs, dep, color=col, lw=2.5, marker="o", ms=5, label=dt.capitalize())
    a2.plot(hrs, tti, color=col, lw=2.5, marker="o", ms=5, label=dt.capitalize())
    NUM[f"tti_peak_{dt}"] = (max(tti), tti.index(max(tti)))
    NUM[f"dep_peak_{dt}"] = (max(dep), dep.index(max(dep)))
    NUM[f"dep_total_{dt}"] = sum(dep)
a1.set_ylabel("Human trips\nstarting per hour"); a1.set_title("Baseline traffic (no hazards): demand and congestion by hour, mean of 20 days")
a1.legend(loc="upper left", fontsize=12)
a2.set_ylabel("Travel-time index\n(1.0 = free-flow)"); a2.set_ylim(0.95, None)
a2.set_xticks(range(0, 24, 3)); a2.set_xticklabels([f"{x:02d}:00" for x in range(0, 24, 3)]); a2.set_xlabel("Hour of day")
wd = NUM["tti_peak_weekday"]
a2.annotate(f"Weekday peak {wd[0]:.2f} at {wd[1]:02d}:00", (wd[1], wd[0]), (wd[1] + 1.2, wd[0] + 0.02), fontsize=12, color=INK2,
            arrowprops=dict(arrowstyle="-", color=MUTED))
fig.text(0.01, 0.01, "Travel-time index = mean over edge entries of (congested time / free-flow time). Capacity calibrated to Caltrans D7 freeway delay per mile.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig06_congestion_by_hour.png", dpi=200); plt.close(fig)

# ---- F7 sweep heatmap
cells = defaultdict(list)
for r in by["sweep"]:
    u, v, start, dur = r["kw"]["forced_blocks"][0]
    d = r["summary"]["human_total_delay_min"] - base[r["seed"]]["summary"]["human_total_delay_min"]
    cells[(u, v, start // 60)].append(d)
edges = [(u, v) for u, v, _ in EDGES]
cls = {(u, v): c for u, v, c in EDGES}
H = list(range(0, 24, 2))
M = {e: [st.mean(cells[(e[0], e[1], h)]) for h in H] for e in edges}
order = sorted(edges, key=lambda e: -sum(M[e]))
NUM["sweep"] = {f"{NODES[e[0]]} - {NODES[e[1]]}": [round(x) for x in M[e]] for e in order}
ramp = ["#ffffff", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
cmap = LinearSegmentedColormap.from_list("b", ramp)
fig, ax = plt.subplots(figsize=(13, 7.4))
ax.grid(False)
data = [[max(x, 0) for x in M[e]] for e in order]
vmax = max(max(r) for r in data)
im = ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=vmax)
for i, row in enumerate(data):
    for j, x in enumerate(row):
        if x >= 500:
            ax.text(j, i, f"{x/1000:.1f}k", ha="center", va="center", fontsize=9.5, color="white" if x > 0.45 * vmax else INK)
ax.set_yticks(range(len(order))); ax.set_yticklabels([f"{NODES[u]} – {NODES[v]}  ({cls[(u, v)]})" for u, v in order], fontsize=11)
ax.set_xticks(range(len(H))); ax.set_xticklabels([f"{h:02d}:00" for h in H], fontsize=11)
ax.set_xlabel("Hour the 60-minute closure starts")
cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01); cb.set_label("Extra human delay (min/day)", color=INK2); cb.outline.set_visible(False)
ax.set_title("Same closure, different hour: extra delay from closing one edge for 60 minutes")
for s in ax.spines.values(): s.set_visible(False)
fig.text(0.01, 0.01, "Each cell = mean of 3 weekdays (same trips with and without the closure). Numbers shown for cells ≥ 500 min. Edges sorted by total across the day.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig07_sweep_heatmap.png", dpi=200); plt.close(fig)

# ---- F8 hazard contributions
labels = [("row1", "Row 1: human incident,\nreduced capacity"), ("row2", "Row 2: human incident,\nedge closed"),
          ("row4", "Row 4: AV incident,\nreduced capacity"), ("all", "All rows together\n(1, 2, 4, 5, 9, 10)")]
res = []
for k, lab in labels:
    diffs = [r["summary"]["human_total_delay_min"] - base[r["seed"]]["summary"]["human_total_delay_min"] for r in by[k]]
    m, h = ci(diffs); res.append((lab, m, h)); NUM[f"contrib_{k}"] = (round(m), round(h), len(diffs))
basemean = st.mean(b["summary"]["human_total_delay_min"] for b in base.values()); NUM["base_delay"] = round(basemean)
fig, ax = plt.subplots(figsize=(13, 5.6))
ys = list(range(len(res)))[::-1]
for y, (lab, m, h), col in zip(ys, res, (BLUE, BLUE, BLUE, INK2)):
    ax.barh(y, m, height=0.55, color=col, alpha=0.9 if col == BLUE else 0.55)
    ax.errorbar(m, y, xerr=h, color=INK, capsize=6, lw=1.6)
    ax.text(m + h + 40, y, f"+{m:,.0f} min/day  (±{h:,.0f})", va="center", fontsize=12.5, color=INK)
ax.set_yticks(ys); ax.set_yticklabels([r[0] for r in res], fontsize=12.5)
ax.set_xlabel("Extra human delay vs. the congestion-only baseline (minutes per day)")
ax.set_xlim(0, max(m + h for _, m, h in res) * 1.35); ax.grid(axis="y", visible=False)
ax.set_title("Frequent minor incidents add at least as much delay as rare full closures")
fig.text(0.01, 0.01, f"Mean of 100 weekdays per bar, paired with the same day's baseline (baseline = {basemean:,.0f} min/day). Whiskers = 95% CI. Row 5 fired 0 times in 100 days; rows 9-10 add no human delay.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig08_hazard_contributions.png", dpi=200); plt.close(fig)
# AV metrics under all hazards
for key in ("av_mean_wait_min", "av_unserved", "human_min_stuck_on_blocked_edges", "peak_hour_tti", "av_share_of_vmt", "human_trips_rerouted"):
    NUM["all_" + key] = (round(st.mean(r["summary"][key] for r in by["all"]), 3), round(st.mean(b["summary"][key] for b in base.values()), 3))

# ---- F9 rate validation
prof = load_profiles()
ev_count = defaultdict(lambda: [0] * 24)
for r in by["all"]:
    for row, h in r["event_hours"]:
        ev_count[row][h] += 1
n = len(by["all"])
exp_day = {"1": EDGE_HAZARDS["1"]["H"] * 24, "2": EDGE_HAZARDS["2"]["H"] * 24, "4": EDGE_HAZARDS["4"]["H"] * 24,
           "5": EDGE_HAZARDS["5"]["H"] * 24, "9": 10 * NODE_HAZARDS["9"]["per_year"] / 365, "10": 10 * NODE_HAZARDS["10"]["per_year"] / 365}
sim_day = {k: sum(ev_count[k]) / n for k in exp_day}
NUM["rates"] = {k: (round(exp_day[k], 4), round(sim_day[k], 4)) for k in exp_day}
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.4), gridspec_kw={"width_ratios": [1, 1.4]})
rows_ = ["1", "4", "2", "9"]
x = range(len(rows_))
a1.bar([i - 0.18 for i in x], [exp_day[k] for k in rows_], width=0.34, color=AXIS, label="Expected from table (H × 24)")
a1.bar([i + 0.18 for i in x], [sim_day[k] for k in rows_], width=0.34, color=BLUE, label="Simulated, mean of 100 days")
a1.set_yscale("log"); a1.set_xticks(list(x)); a1.set_xticklabels([f"Row {k}" for k in rows_])
a1.set_ylabel("Events per day (log scale)"); a1.legend(fontsize=10.5, loc="upper right"); a1.set_title("Daily counts match the table")
for i, k in enumerate(rows_):
    a1.text(i + 0.18, sim_day[k] * 1.25, f"{sim_day[k]:.2f}" if sim_day[k] < 10 else f"{sim_day[k]:.0f}", ha="center", fontsize=10.5, color=INK)
sim_h = [c / n for c in ev_count["1"]]
exp_h = [EDGE_HAZARDS["1"]["H"] * 24 * prof["human_vmt_weekday"][h] for h in range(24)]
a2.bar(range(24), sim_h, color=BLUE, width=0.75, label="Simulated row-1 events")
a2.plot(range(24), exp_h, color=INK, lw=2, label="Expected: H × 24 × hour's VMT share")
a2.set_xticks(range(0, 24, 3)); a2.set_xticklabels([f"{h:02d}" for h in range(0, 24, 3)]); a2.set_xlabel("Hour")
a2.set_ylabel("Row-1 events per hour"); a2.set_ylim(0, 20); a2.legend(fontsize=10.5, loc="upper left"); a2.set_title("…and cluster where the traffic is")
fig.tight_layout(); fig.savefig(OUT + "fig13_rate_validation.png", dpi=200); plt.close(fig)

# ---- F10 depot outage grid
bunserved = {r["seed"]: r["summary"]["av_unserved"] for r in by["dep_base"]}
breq = {r["seed"]: r["summary"]["av_requests"] for r in by["dep_base"]}
G = defaultdict(list)
for r in by["dep"]:
    outs = r["kw"]["forced_outages"]; k = len(outs); dur = outs[0][2] / 60
    G[(k, dur)].append(100 * (r["summary"]["av_unserved"] - bunserved[r["seed"]]) / breq[r["seed"]])
durs = [2, 4, 6, 8, 10, 12]
Z = [[st.mean(G[(k, d)]) for d in durs] for k in (1, 2, 3, 4)]
NUM["dep_grid"] = {k: [round(x, 1) for x in Z[k - 1]] for k in (1, 2, 3, 4)}
NUM["dep_base_unserved"] = (st.mean(bunserved.values()), st.mean(breq.values()))
fig, ax = plt.subplots(figsize=(13, 5.0)); ax.grid(False)
oramp = ["#ffffff", "#fde3d6", "#f9c3a8", "#f39c74", "#eb6834", "#c4501f", "#933a14"]
im = ax.imshow(Z, aspect="auto", cmap=LinearSegmentedColormap.from_list("o", oramp), vmin=0, vmax=max(max(r) for r in Z), origin="lower")
for i, row in enumerate(Z):
    for j, x in enumerate(row):
        ax.text(j, i, f"{x:.0f}%", ha="center", va="center", fontsize=13, color="white" if x > 0.5 * max(max(r) for r in Z) else INK)
ax.set_xticks(range(len(durs))); ax.set_xticklabels([f"{d} h" for d in durs]); ax.set_xlabel("Outage length (all start at 10:00)")
ax.set_yticks(range(4)); ax.set_yticklabels(["1 of 4", "2 of 4", "3 of 4", "all 4"]); ax.set_ylabel("Depots dark")
cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.01); cb.set_label("Extra AV requests lost (% of day's requests)", color=INK2); cb.outline.set_visible(False)
for s in ax.spines.values(): s.set_visible(False)
ax.set_title("AV trips are lost only when EVERY depot is dark for several hours")
fig.text(0.01, 0.01, "Notes' 4-depot layout (Santa Monica, Sawtelle, LAX, Culver City). Each cell = mean over every combination of dark depots × 3 weekdays, vs. the same days with no outage.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(OUT + "fig09_depot_outage_grid.png", dpi=200); plt.close(fig)

# ---- AV service by hour, 4 dark 10 h
def hourly_mean(kind, key):
    return [st.mean(r["hourly"][h][key] for r in by[kind]) for h in range(24)]
sb, ss, su = hourly_mean("avsvc_base", "av_served"), hourly_mean("avsvc", "av_served"), hourly_mean("avsvc", "av_unserved")
NUM["avsvc_tot"] = (round(sum(sb), 1), round(sum(ss), 1), round(sum(su), 1), round(st.mean(r["summary"]["av_requests"] for r in by["avsvc"]), 1))
fig, ax = plt.subplots(figsize=(13, 5.2))
ax.axvspan(9.5, 19.5, color=RED, alpha=0.07)
ax.text(14.5, max(sb) * 1.18, "All 4 depots dark 10:00–20:00", ha="center", fontsize=12.5, color=INK)
ax.bar(range(24), su, color=RED, width=0.7, alpha=0.85, label="Requests lost (scenario)")
ax.plot(range(24), sb, color=INK2, lw=2.2, ls=(0, (5, 3)), marker="o", ms=4, label="Requests served, no outage")
ax.plot(range(24), ss, color=BLUE, lw=2.6, marker="o", ms=5, label="Requests served, with outage")
ax.set_xticks(range(0, 24, 3)); ax.set_xticklabels([f"{h:02d}:00" for h in range(0, 24, 3)]); ax.set_ylim(0, max(sb) * 1.3)
ax.set_ylabel("AV requests per hour"); ax.set_xlabel("Hour the request was made"); ax.legend(loc="upper left", fontsize=11.5)
ax.set_title("When every depot is dark, the fleet runs down its batteries and stops accepting trips")
fig.text(0.01, 0.01, "Mean of 10 weekdays, notes' 4-depot layout, 15 AVs. AVs keep driving while they have range; with no working depot they must keep 50 mi in hand.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig09b_av_service_outage.png", dpi=200); plt.close(fig)
json.dump(NUM, open(RES / "numbers.json", "w"), indent=1)
print(json.dumps(NUM, indent=1))

# ======================= siting check ======================= #
res = json.load(open(RES / "siting_check.json"))
res.sort(key=lambda r: r["wait"])
short = {1: "SM", 2: "Saw", 3: "WeHo", 4: "LAX", 5: "Culver", 6: "DTLA", 7: "Playa", 8: "Mid", 9: "Hwd", 10: "Pas"}
lab = lambda c: ", ".join(short[n] for n in c)
notes = next(i for i, r in enumerate(res) if tuple(r["combo"]) == (1, 2, 4, 5))
fig, ax = plt.subplots(figsize=(13, 5.8))
x = list(range(1, len(res) + 1)); w = [r["wait"] for r in res]
cols = [ORANGE if i == notes else (BLUE if i < 5 else "#9ec5f4") for i in range(len(res))]
ax.bar(x, w, color=cols, width=0.85, edgecolor="none")
ax.set_xlim(0, len(res) + 1); ax.set_ylim(0, 11.5)
ax.set_xlabel("Layout rank (1 = shortest average AV wait), all 210 ways to place 4 depots"); ax.set_ylabel("Mean AV wait (min)")
b = res[0]
ax.annotate(f"#1: {lab(b['combo'])}\n{b['wait']:.1f} min wait, {100*b['empty']:.0f}% empty miles", (1, b["wait"]), (18, 10.4),
            fontsize=12, color=INK, arrowprops=dict(arrowstyle="-", color=INK2))
n = res[notes]
ax.annotate(f"Notes' layout {{1, 2, 4, 5}}: #{notes+1} of 210\n{lab(n['combo'])}: {n['wait']:.1f} min wait, {100*n['empty']:.0f}% empty miles",
            (notes + 1, n["wait"]), (120, 10.4), fontsize=12, color=INK, ha="center", arrowprops=dict(arrowstyle="-", color=ORANGE, lw=1.5))
ax.set_title("Where the depots go changes AV service even on a normal day")
fig.text(0.01, 0.01, "Each bar = mean of 2 weekdays, no hazards, uniform trip origins/destinations (gravity model not yet in). Unserved requests were 0–0.5 per day for every layout.", fontsize=10, color=MUTED)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT + "fig14_siting_check.png", dpi=200); plt.close(fig)
print(notes + 1, b, n)
