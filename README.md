# Istanbul route map

A map of Istanbul's road public transport at true scale, drawn like a city bus map: every İETT bus line
(Metrobüs included), every minibüs line and every taksi-dolmuş line, with every stop named. The lines are straightened to
45° and 90° over the real coastline, the Bosphorus and the lakes.

![Overview](out/istanbul-route-map-overview.png)

- **The map:** [`out/istanbul-route-map.svg`](out/istanbul-route-map.svg) (30,470 × 14,516 px, about 185 px per km). Open it in a browser and zoom in.
- **Full-resolution PNG tiles,** 4 columns × 3 rows: [`out/tiles/`](out/tiles/) (`tile-r1-c1.png` is the top left).
- **The overview above,** at a quarter of the size: [`out/istanbul-route-map-overview.png`](out/istanbul-route-map-overview.png).

## What's on it

| | |
|---|---|
| İETT bus lines (Metrobüs included) | 772 of 782 (the other 10 are depot runs, the spare-fleet code, the Büyükada taxi and the Tünel funicular) |
| Minibüs lines | 156 |
| Taksi-dolmuş lines | 18 |
| Stops | 10,592 places, every one named |
| Data | 9 November 2026 |

How to read it:
- **Corridors:** each one runs at 0°, 45° or 90°. Its thickness and shade show how many lines share it.
  - İETT buses are blue, the Metrobüs red, minibüs green, and taksi-dolmuş dashed orange.
  - Route numbers are printed in tags along the corridors, and every line is named at least once.
- **Places:** both sides of a road count as one place, as do same-name stops within 300 m (never across the Metrobüs).
  - Minibüs and dolmuş stops join an İETT stop of the same name within 150 m.
  - Interchanges, terminals and branch points are circles; stops in between are small dots, spaced evenly along the corridor. No line is squished: every stop has at least one grid step (about 230 m, 42 px) to itself. Where a corridor would be too short for its stops, the stops in its middle get grid points of their own, until there's room.
  - Names along level corridors are set at 45°. Where a name has no room beside its stop, it moves further out with a thin leader line. **No text overlaps**: no name or route tag touches another one or a stop dot. Text is sized with each character's real width, the widest of the common sans-serif fonts, and the real height above and below the line (accents on capitals included). If anything had no room, the whole map would be drawn larger until it did. `make check` measures every name and tag as Chrome draws it and reports any overlap: 0.
- **Geography:** true scale everywhere, from Silivri to Şile, so nothing is squished at the edges.
  - Places are snapped to a grid of about 230 m. A place moves only where two stops would share a grid point: by a median of 108 m, 95 % within 268 m, at most 723 m.
  - Corridors bend where their real roads bend.
  - The land, the sea (the Bosphorus and the Golden Horn included) and the lakes come from OpenStreetMap's coastline and water areas.

## How it's made

```
make data     # download everything (see Data below); stop orders take about 15 min at one request a second
make map      # compile the minibüs/dolmuş routes and draw out/istanbul-route-map.svg (a few seconds)
make images   # the overview PNG and the tiles (needs: cd tools && npm install, and Google Chrome)
make check    # every name and route tag measured as Chrome draws it; reports any overlap
```

- `fetch_orders.py`: each İETT line's stop order, one request a second. It can be resumed: lines already fetched are skipped.
- `dolmus_compile.py`: İBB's minibüs data doesn't link stops to lines.
  - Minibüs: a line's stops are the minibüs stops within 30 m of its route, in order along it.
  - Taksi-dolmuş: these stop anywhere, so their stands (within 80 m) and the İETT stops along the route stand in as named places to get on and off. Alternative and depot routes and depot stands are left out, and so are route pieces under 300 m (connectors between branches). A route end with no stop of its own takes the name of the nearest stop within 400 m, or "Güzergah ucu" (route end).
  - The same compiled `data/dolmus.json` feeds the dolmuş legs of the Istanbul Commute integration.
- `schematic.py`: builds the network, keeps the places where something changes, and snaps them to a grid.
  - It splits corridors that are too short for their stops, and draws every corridor with one 45° bend.
  - It places every name with a rotated-box overlap test against the names, tags and stop dots already placed, then the route tags. Every line gets at least one tag.
  - The same data always gives the same map. Layout settings come from the environment: `GEOGRAPHY` (share of true distance, 1 = true scale; lower values spread dense areas instead), `STEPS` (grid steps west to east, 700), `SCALE` (px per step to start from, 32; it grows until every name fits, here to 42.3).
- `tools/measure_chars.js` measures each character's width in the installed fonts, into `tools/charwidths.json`. `tools/check_overlaps.js` is the independent check behind `make check`.

## Data

| File | Source |
|---|---|
| `data/hat.json` | Every İETT line: İBB `HatDurakGuzergah.asmx` `GetHat_json` |
| `data/durak.json` | Every İETT stop with coordinates: same service, `GetDurak_json` |
| `data/lines/*.json` | Each line's stops in order, per direction: iett.istanbul `GetStationForRoute` |
| `data/dolmus/*.geojson` | Minibüs and taksi-dolmuş routes and stops: İBB open data portal, data.ibb.gov.tr (*Minibüs Hatları/Durakları*, *Taksi Dolmuş Hatları/Durakları*, updated 4 November 2026) |
| `data/dolmus.json`, `data/dolmus_shapes.json` | Compiled from the above by `dolmus_compile.py` |
| `data/geo/coastline.json`, `data/geo/water.json` | Coastline, and lakes, reservoirs and lagoons: OpenStreetMap, via the Overpass API. `geo.py` joins the coastline into land shapes |

The data is İBB's and İETT's, published under the İBB Open Data License (İBB Açık Veri Lisansı), which asks for
attribution: *Source: İstanbul Büyükşehir Belediyesi Açık Veri Portalı / İETT*. The land and water are © OpenStreetMap contributors, available under the Open Database License (ODbL).

## License

The code is GPL-3.0 (see `LICENSE`). The data keeps its own license, above.
