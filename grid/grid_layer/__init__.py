"""
Grid layer for the AV fleet resilience simulation (GIRS Project #4).

    from grid_layer import GridLayer, psps, substation_loss, HazardEvent

Modules
  params   - every assumption (limits, ratings, depots, outage rates, hazard zones)
  feeder   - physics: topology, restoration switching, power flow, curtailment
  outages  - routine random line failures (Markov, calibrated to SAIFI/CAIDI)
  hazards  - correlated events injected from the hazard layer (PSPS, earthquake, ...)
  layer    - GridLayer: hourly clock + table outputs; the interface to other layers
  studies  - one-off studies: hosting capacity, N-1, validation
"""

from .feeder import Feeder, FeederState
from .hazards import HazardEvent, psps, substation_loss, zone_event
from .layer import GridLayer, GridRun, HourState
from .outages import Outage, RoutineOutages

__all__ = ["Feeder", "FeederState", "HazardEvent", "psps", "substation_loss", "zone_event",
           "GridLayer", "GridRun", "HourState", "Outage", "RoutineOutages"]
