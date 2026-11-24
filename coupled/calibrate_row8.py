"""
Calibrate row 8 (AV obstructs incident clearance) so the simulated rate matches the table:
0.17 obstruction incidents per AV-year [DOC, SFFD 2023].

    python -m coupled.calibrate_row8

Counts, on ordinary weekdays, how many row 1-3 incidents start on an edge with an AV on it
('amp_present'), then sets  p = 0.17 x n_AV / (365 x present_per_day).
"""
import numpy as np

from . import config as C
from .scenarios import ordinary
from .sim import CoupledSim
from grid_layer.feeder import Feeder
from av_traffic_sim_tod import load_profiles


def main(n=20):
    f, prof = Feeder(), load_profiles()
    built = set(C.EXISTING_DEPOTS)
    pres = [CoupledSim(s, [C.WAYMO], {"Waymo": built}, built, ordinary(None), f, profiles=prof)
            .run().metrics()["amp_present"] for s in range(n)]
    per_day = float(np.mean(pres))
    p = C.AMP_PER_AV_YEAR * C.WAYMO["n_av"] / (365 * per_day)
    print(f"incidents starting with an AV on the edge: {per_day:.1f}/day (seeds 0-{n - 1})")
    print(f"AMP_P_GIVEN_PRESENT = {p:.6f}  -> set it in coupled/config.py")


if __name__ == "__main__":
    main()
