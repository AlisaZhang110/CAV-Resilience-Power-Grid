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
| +6 | Downtown LA | 6.986 | -0.403 | 0.094 | 0.284 | 5.072 | -0.038 | -0.329 |
| +9 | Hollywood | 7.071 | -0.318 | 0.081 | 0.268 | 5.074 | -0.036 | -0.250 |
| +8 | Mid-City | 7.173 | -0.216 | 0.100 | 0.278 | 5.072 | -0.038 | -0.289 |
| +10 | Pasadena | 7.195 | -0.193 | 0.103 | 0.262 | 5.079 | -0.031 | -0.150 |
| +3 | West Hollywood | 7.343 | -0.046 | 0.095 | 0.294 | 5.098 | -0.012 | 0.000 |
| +7 | Playa del Rey | 7.388 | -0.001 | 0.057 | 0.311 | 5.102 | -0.008 | 0.001 |
| base | (none) | 7.389 | 0.000 | 0.000 | 0.307 | 5.110 | 0.000 | 0.000 |


## Multi-fleet (Waymo 15 AVs + Tesla), annual-weighted rider wait (min)

| Tesla AVs | Config | All | Waymo | Tesla | Unserved % | Human delay | Charge queue (min/day, ordinary) |
|---|---|---|---|---|---|---|---|
| 5 | T5:universal+9 | 8.983 | 7.048 | 15.061 | 0.619 | 5.098 | 4.9 |
| 5 | T5:universal+6 | 8.998 | 7.087 | 15.027 | 0.710 | 5.101 | 4.4 |
| 5 | T5:universal+3 | 9.284 | 7.183 | 15.949 | 0.648 | 5.157 | 1.5 |
| 5 | T5:universal+10 | 9.321 | 7.377 | 15.481 | 0.558 | 5.101 | 3.2 |
| 5 | T5:universal+8 | 9.487 | 7.442 | 15.930 | 0.620 | 5.105 | 3.3 |
| 5 | T5:universal+7 | 9.682 | 7.684 | 16.022 | 0.676 | 5.156 | 5.8 |
| 5 | T5:exclusive+6 | 9.724 | 8.023 | 15.069 | 0.739 | 5.158 | 8.3 |
| 5 | T5:exclusive+7 | 9.735 | 7.796 | 15.865 | 1.036 | 5.159 | 7.6 |
| 5 | T5:shared_existing | 9.852 | 7.849 | 16.199 | 0.677 | 5.164 | 11.7 |
| 5 | T5:exclusive+10 | 9.855 | 7.701 | 16.691 | 1.107 | 5.135 | 5.0 |
| 5 | T5:exclusive+9 | 9.870 | 7.946 | 15.958 | 0.845 | 5.165 | 6.4 |
| 5 | T5:exclusive+8 | 9.896 | 8.000 | 15.876 | 0.952 | 5.149 | 4.7 |
| 5 | T5:exclusive+3 | 9.989 | 8.024 | 16.226 | 0.830 | 5.178 | 5.7 |
| 10 | T10:universal+9 | 8.425 | 7.281 | 10.022 | 0.204 | 5.304 | 8.2 |
| 10 | T10:universal+6 | 8.452 | 7.155 | 10.339 | 0.203 | 5.320 | 9.2 |
| 10 | T10:universal+8 | 8.588 | 7.486 | 10.120 | 0.181 | 5.311 | 10.4 |
| 10 | T10:universal+3 | 8.883 | 7.928 | 10.208 | 0.203 | 5.361 | 6.7 |
| 10 | T10:universal+7 | 8.887 | 7.803 | 10.392 | 0.199 | 5.364 | 11.0 |
| 10 | T10:shared_existing | 8.955 | 7.894 | 10.428 | 0.268 | 5.372 | 20.1 |
| 10 | T10:exclusive+6 | 9.234 | 7.691 | 11.415 | 0.340 | 5.417 | 18.4 |
| 10 | T10:exclusive+8 | 9.306 | 8.092 | 10.998 | 0.156 | 5.399 | 13.9 |
| 10 | T10:universal+10 | 9.315 | 7.872 | 11.341 | 0.179 | 5.332 | 5.4 |
| 10 | T10:exclusive+9 | 9.367 | 7.824 | 11.511 | 0.292 | 5.374 | 27.9 |
| 10 | T10:exclusive+3 | 9.691 | 7.851 | 12.291 | 0.299 | 5.396 | 16.4 |
| 10 | T10:exclusive+7 | 9.882 | 8.047 | 12.489 | 0.548 | 5.399 | 20.0 |
| 10 | T10:exclusive+10 | 9.885 | 7.742 | 12.957 | 0.292 | 5.395 | 17.0 |
| 15 | T15:universal+9 | 7.081 | 7.181 | 6.983 | 0.161 | 5.416 | 12.4 |
| 15 | T15:universal+6 | 7.285 | 7.403 | 7.154 | 0.161 | 5.445 | 11.4 |
| 15 | T15:universal+8 | 7.303 | 7.384 | 7.238 | 0.143 | 5.443 | 13.3 |
| 15 | T15:universal+10 | 7.552 | 7.533 | 7.574 | 0.124 | 5.446 | 6.3 |
| 15 | T15:universal+3 | 7.552 | 7.959 | 7.120 | 0.161 | 5.480 | 10.1 |
| 15 | T15:shared_existing | 7.655 | 8.049 | 7.221 | 0.181 | 5.506 | 30.6 |
| 15 | T15:exclusive+6 | 7.738 | 7.860 | 7.591 | 0.217 | 5.528 | 25.3 |
| 15 | T15:universal+7 | 7.755 | 8.040 | 7.438 | 0.201 | 5.524 | 20.4 |
| 15 | T15:exclusive+9 | 8.067 | 8.046 | 8.047 | 0.236 | 5.541 | 32.0 |
| 15 | T15:exclusive+8 | 8.165 | 7.977 | 8.364 | 0.219 | 5.553 | 22.9 |
| 15 | T15:exclusive+7 | 8.188 | 7.991 | 8.404 | 0.236 | 5.539 | 31.7 |
| 15 | T15:exclusive+3 | 8.224 | 8.034 | 8.417 | 0.162 | 5.531 | 35.7 |
| 15 | T15:exclusive+10 | 8.918 | 7.757 | 10.092 | 0.386 | 5.579 | 40.5 |

