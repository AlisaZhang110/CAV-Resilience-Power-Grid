# Coupled simulation results

## Scenario rates used for annual weighting

| Scenario | Rows | Events / yr | Days per event | Basis |
|---|---|---|---|---|
| Rain day | 1b | 34.1 | 1 | [DOC] NOAA normals, 34.1 rain days/yr |
| Line fault (unplanned) | 9 | 3.976 | 1 | [DOC] SCE SAIFI 0.904 -> 0.124/line-yr x 32 lines |
| Planned outage | 11 | 1.37 | 1 | [DOC] SCE planned SAIFI 0.311 -> 0.043/line-yr x 32 lines |
| Major event day (storm) | 10 | 0.3743 | 1 | [DOC] 0.1834/customer-yr / 0.49 mean share interrupted |
| PSPS (WUI zone) | 12 | 0.5 | 1.5 | [DOC] 5 LA County events/yr x q = 0.10 [ASSUMPTION; q is a GAP] |
| Wildfire, 1 edge closed | 13 | 0.1108 | 10 | [DOC] column H; median closure 1-2 weeks -> 10 days |
| Wildfire, 3 edges + PSPS | 14 (+12) | 0.01598 | 1.5 | [DOC] column H; common-cause wind event |
| Flood, 100-yr edge | 15 | 0.008 | 1 | [DOC] 0.8%/yr per SFHA edge x 1 edge |
| Flood, 500-yr regional | 16 | 0.002 | 2 | [DOC] 0.2%/yr regional AEP |
| Earthquake M>=6.7 | 18 | 0.02291 | 1 | [DOC] UCERF3 0.0305/yr x P(>=3 edges | event) = 0.75 [ASSUMPTION, table range 0.5-1.0] |
| AV fleet stall (Waymo) | 7 | 0.0831 | 1 | [DOC] column H (scenario row, ~1/yr city-wide x area factor) |

## Placement (Waymo, 15 AVs, existing depots 1, 2, 4, 5 + one candidate)

| Config | Site | Rider wait (min) | Δ wait vs base | SE | Unserved % | Human delay (min/trip) | Δ human delay | Mean Δ wait over hazard scenarios |
|---|---|---|---|---|---|---|---|---|
| +6 | Downtown LA | 7.264 | -0.515 | 0.105 | 0.291 | 5.079 | -0.036 | -0.415 |
| +9 | Hollywood | 7.282 | -0.497 | 0.090 | 0.276 | 5.078 | -0.037 | -0.408 |
| +8 | Mid-City | 7.442 | -0.336 | 0.101 | 0.303 | 5.084 | -0.031 | -0.366 |
| +10 | Pasadena | 7.508 | -0.271 | 0.116 | 0.303 | 5.080 | -0.035 | -0.237 |
| +3 | West Hollywood | 7.594 | -0.185 | 0.083 | 0.298 | 5.098 | -0.017 | -0.107 |
| +7 | Playa del Rey | 7.778 | -0.001 | 0.052 | 0.328 | 5.113 | -0.002 | 0.008 |
| base | (none) | 7.779 | 0.000 | 0.000 | 0.348 | 5.115 | 0.000 | 0.000 |


## Multi-fleet (Waymo 15 AVs + Tesla), annual-weighted rider wait (min)

| Tesla AVs | Config | All | Waymo | Tesla | Unserved % | Human delay | Charge queue (min/day, ordinary) |
|---|---|---|---|---|---|---|---|
| 5 | T5:universal+6 | 9.398 | 7.445 | 15.596 | 0.798 | 5.119 | 12.0 |
| 5 | T5:universal+9 | 9.480 | 7.607 | 15.417 | 0.889 | 5.117 | 19.3 |
| 5 | T5:universal+10 | 9.725 | 7.770 | 15.933 | 0.741 | 5.103 | 10.4 |
| 5 | T5:universal+8 | 9.773 | 7.781 | 16.135 | 0.860 | 5.109 | 11.1 |
| 5 | T5:exclusive+6 | 9.871 | 7.973 | 15.867 | 0.947 | 5.167 | 22.4 |
| 5 | T5:universal+3 | 9.960 | 7.872 | 16.570 | 0.556 | 5.173 | 6.7 |
| 5 | T5:shared_existing | 9.972 | 8.113 | 15.848 | 0.794 | 5.174 | 32.7 |
| 5 | T5:universal+7 | 10.059 | 8.233 | 15.885 | 0.769 | 5.168 | 17.1 |
| 5 | T5:exclusive+9 | 10.152 | 8.098 | 16.666 | 0.933 | 5.165 | 13.6 |
| 5 | T5:exclusive+7 | 10.175 | 8.140 | 16.562 | 1.092 | 5.192 | 25.1 |
| 5 | T5:exclusive+8 | 10.190 | 8.116 | 16.709 | 1.068 | 5.168 | 25.3 |
| 5 | T5:exclusive+10 | 10.205 | 7.938 | 17.404 | 1.405 | 5.161 | 21.3 |
| 5 | T5:exclusive+3 | 10.265 | 8.078 | 17.162 | 1.100 | 5.177 | 10.3 |
| 10 | T10:universal+6 | 8.943 | 7.701 | 10.686 | 0.295 | 5.331 | 25.3 |
| 10 | T10:universal+9 | 9.062 | 7.969 | 10.569 | 0.342 | 5.345 | 27.9 |
| 10 | T10:universal+8 | 9.085 | 7.993 | 10.594 | 0.349 | 5.320 | 24.0 |
| 10 | T10:universal+3 | 9.310 | 7.740 | 11.571 | 0.462 | 5.367 | 17.3 |
| 10 | T10:shared_existing | 9.358 | 8.221 | 10.969 | 0.298 | 5.355 | 67.1 |
| 10 | T10:universal+7 | 9.472 | 8.246 | 11.223 | 0.431 | 5.374 | 54.6 |
| 10 | T10:exclusive+9 | 9.528 | 7.919 | 11.756 | 0.343 | 5.392 | 74.7 |
| 10 | T10:exclusive+8 | 9.598 | 8.044 | 11.780 | 0.384 | 5.410 | 91.9 |
| 10 | T10:exclusive+6 | 9.683 | 8.136 | 11.847 | 0.341 | 5.424 | 91.1 |
| 10 | T10:universal+10 | 9.822 | 8.243 | 12.054 | 0.483 | 5.348 | 28.5 |
| 10 | T10:exclusive+7 | 9.962 | 7.923 | 12.891 | 0.421 | 5.399 | 82.0 |
| 10 | T10:exclusive+3 | 9.989 | 7.909 | 12.960 | 0.481 | 5.401 | 91.8 |
| 10 | T10:exclusive+10 | 10.298 | 7.803 | 13.874 | 0.936 | 5.415 | 108.7 |
| 15 | T15:universal+6 | 7.354 | 7.470 | 7.261 | 0.238 | 5.418 | 29.0 |
| 15 | T15:universal+9 | 7.393 | 7.528 | 7.239 | 0.238 | 5.462 | 30.2 |
| 15 | T15:universal+8 | 7.606 | 7.673 | 7.544 | 0.162 | 5.457 | 31.8 |
| 15 | T15:universal+3 | 7.756 | 8.109 | 7.391 | 0.296 | 5.501 | 40.8 |
| 15 | T15:universal+10 | 7.902 | 7.565 | 8.272 | 0.160 | 5.473 | 20.1 |
| 15 | T15:universal+7 | 7.912 | 8.169 | 7.624 | 0.255 | 5.524 | 62.3 |
| 15 | T15:shared_existing | 7.954 | 8.202 | 7.673 | 0.276 | 5.530 | 90.7 |
| 15 | T15:exclusive+6 | 8.206 | 8.216 | 8.167 | 0.364 | 5.515 | 156.3 |
| 15 | T15:exclusive+9 | 8.370 | 8.410 | 8.292 | 0.369 | 5.568 | 195.2 |
| 15 | T15:exclusive+8 | 8.380 | 8.428 | 8.325 | 0.442 | 5.554 | 151.7 |
| 15 | T15:exclusive+7 | 8.724 | 8.309 | 9.155 | 0.273 | 5.567 | 179.7 |
| 15 | T15:exclusive+3 | 8.816 | 8.565 | 9.055 | 0.275 | 5.570 | 191.5 |
| 15 | T15:exclusive+10 | 9.475 | 8.336 | 10.611 | 0.539 | 5.588 | 272.5 |


## Energy use: 2.0 mi/kWh (main) vs 3.5 mi/kWh (earlier value)

| Config | Rider wait at 3.5 | Δ vs existing 4 | Rider wait at 2.0 | Δ vs existing 4 |
|---|---|---|---|---|
| base | 7.389 | +0.000 | 7.779 | +0.000 |
| +3 | 7.343 | -0.046 | 7.594 | -0.185 |
| +6 | 6.986 | -0.403 | 7.264 | -0.515 |
| +7 | 7.388 | -0.001 | 7.778 | -0.001 |
| +8 | 7.173 | -0.216 | 7.442 | -0.336 |
| +9 | 7.071 | -0.318 | 7.282 | -0.497 |
| +10 | 7.195 | -0.193 | 7.508 | -0.271 |
