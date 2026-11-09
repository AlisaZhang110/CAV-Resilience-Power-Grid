"""
Rebuild demand_profiles.csv from the 2017 NHTS public trip file.

Download "CSV (80 MB)" from https://nhts.ornl.gov/downloads (2017 NHTS), unzip, then:
    python build_profiles.py path/to/trippub.csv

Filters (2017 NHTS codebook):
  human_*  : HH_CBSA == 31080 (Los Angeles-Long Beach-Anaheim), TRPTRANS in 03-06
             (car, SUV, van, pickup), DRVR_FLG == 01 (respondent was the driver)
             -> one row per household-vehicle trip, not per passenger
  av_*     : TRPTRANS == 17 (taxi/limo, including Uber/Lyft), ALL US households.
             The LA-CBSA subsample is only 193 trips, so the national profile is used.
  weekday  : TRAVDAY 2-6; weekend: TRAVDAY 1 or 7
  hour     : floor(STRTTIME / 100)
  weights  : WTTRDFIN (trip weight); *_vmt_* columns weight each trip by VMT_MILE
  *_n_*    : unweighted sample count in that hour (small n = noisy hour)

Output columns are percentages of the day's trips (or VMT) starting in each hour.
"""
import csv
import sys
from collections import defaultdict


def main(path):
    acc = defaultdict(lambda: [0.0] * 24)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                h = int(r["STRTTIME"]) // 100 % 24
                w = float(r["WTTRDFIN"])
                tt = int(r["TRPTRANS"])
                day = int(r["TRAVDAY"])
            except ValueError:
                continue
            kind = "weekend" if day in (1, 7) else "weekday"
            vmt = max(float(r["VMT_MILE"] or 0), 0.0)
            if r["HH_CBSA"] == "31080" and 3 <= tt <= 6 and r["DRVR_FLG"] in ("01", "1"):
                acc[f"human_trips_{kind}"][h] += w
                acc[f"human_vmt_{kind}"][h] += w * vmt
                acc[f"human_n_{kind}"][h] += 1
            if tt == 17:
                acc[f"av_trips_{kind}"][h] += w
                acc[f"av_n_{kind}"][h] += 1

    cols = ["human_trips_weekday", "human_vmt_weekday", "human_n_weekday",
            "human_trips_weekend", "human_vmt_weekend", "human_n_weekend",
            "av_trips_weekday", "av_n_weekday", "av_trips_weekend", "av_n_weekend"]
    with open("demand_profiles.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hour"] + cols)
        for h in range(24):
            row = [h]
            for c in cols:
                v = acc[c]
                row.append(int(v[h]) if "_n_" in c else round(100 * v[h] / sum(v), 2))
            w.writerow(row)
    print("wrote demand_profiles.csv")


if __name__ == "__main__":
    main(sys.argv[1])
