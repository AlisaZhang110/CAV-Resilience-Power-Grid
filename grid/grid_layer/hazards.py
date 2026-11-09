"""
hazards.py -- correlated, multi-element events injected into the grid.

The hazard layer (your Failure Mode Table: PSPS, wildfire, flood, earthquake,
major storms) decides THAT an event happens, WHEN, for HOW LONG and WHERE. It
hands the grid layer a HazardEvent naming which lines / buses / substation are
knocked out. The grid layer then works out the consequences.

This keeps the two concerns separate: hazard probabilities live in the hazard
layer; grid physics lives in feeder.py.
"""

from dataclasses import dataclass, field

from . import params as P
from .outages import Outage


@dataclass
class HazardEvent:
    name: str                       # e.g. "PSPS", "earthquake", "flood"
    start_h: float                  # hours from simulation start
    duration_h: float
    lines: list = field(default_factory=list)
    buses: list = field(default_factory=list)
    substation: bool = False

    def to_outages(self):
        end = self.start_h + self.duration_h
        out = [Outage("line", ln, self.start_h, end, self.name) for ln in self.lines]
        out += [Outage("bus", b, self.start_h, end, self.name) for b in self.buses]
        if self.substation:
            out.append(Outage("substation", -1, self.start_h, end, self.name))
        return out


# ---------------- convenience builders ----------------
def zone_event(name, zone, start_h, duration_h, p_fail=1.0, rng=None, whole_zone_dark=False):
    """
    Lines in a hazard zone (params.LINE_ZONES) fail together.

    p_fail < 1        : each line fails independently with that probability,
                        e.g. from a fragility curve at the hazard intensity
                        (damaged lines only; undamaged parts can still be fed)
    whole_zone_dark   : also take out the zone's buses (params.ZONE_BUSES), so
                        nothing inside the zone can be re-fed by switching
    """
    lines = list(P.LINE_ZONES[zone])
    if p_fail < 1.0:
        if rng is None:
            raise ValueError("pass rng when p_fail < 1")
        lines = [ln for ln in lines if rng.random() < p_fail]
    buses = list(P.ZONE_BUSES.get(zone, [])) if whole_zone_dark else []
    return HazardEvent(name, start_h, duration_h, lines=lines, buses=buses)


def psps(start_h, duration_h, zone="WUI"):
    """
    Public Safety Power Shutoff: the utility deliberately de-energizes the whole
    zone. Lines and buses inside it stay dark; switching cannot re-feed them.
    """
    return zone_event("PSPS", zone, start_h, duration_h, whole_zone_dark=True)


def substation_loss(start_h, duration_h, cause="earthquake"):
    """Loss of supply at bus 0: substation damage or loss of the sub-transmission line feeding it."""
    return HazardEvent(cause, start_h, duration_h, substation=True)
