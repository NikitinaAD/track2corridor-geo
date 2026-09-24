# track2corridor-geo

[![CI](https://github.com/NikitinaAD/track2corridor-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/NikitinaAD/track2corridor-geo/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/track2corridor-geo.svg)](https://pypi.org/project/track2corridor-geo/)
[![Python](https://img.shields.io/pypi/pyversions/track2corridor-geo.svg)](https://pypi.org/project/track2corridor-geo/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**Build an auditable centerline and corridor from noisy survey-track points.**

`track2corridor` converts ordered points into a buffered footprint, raster
skeleton, NetworkX graph, centerline, and fixed-width corridor. It exposes every
intermediate geometry and a diagnostics report instead of hiding algorithmic
warnings behind a single polygon.

![Track points become a footprint, centerline, and corridor](https://raw.githubusercontent.com/NikitinaAD/track2corridor-geo/main/docs/demo.svg)

## Quick start

```bash
python -m pip install track2corridor-geo
track2corridor build track.laz \
  --footprint-width 20 \
  --corridor-width 8 \
  --output corridor.gpkg
```

CSV input must contain `x,y` columns and needs an explicit projected CRS:

```bash
track2corridor build track.csv --crs EPSG:32637 --output corridor.gpkg
```

## Reproducible example

Create a deterministic noisy S-shaped track, then build its corridor:

```bash
python examples/make_example.py
track2corridor build examples/noisy-track.csv \
  --crs EPSG:3857 \
  --footprint-width 14 \
  --corridor-width 6 \
  --cell-size 1 \
  --min-branch-length 4 \
  --output examples/corridor.gpkg \
  --diagnostics examples/diagnostics.json
```

The GeoPackage contains three inspectable layers:

| layer | meaning |
|---|---|
| `footprint` | union of point buffers used as raster input |
| `centerline` | graph edges converted back to line geometry |
| `corridor` | fixed-width buffer around the derived centerline |

The JSON report records input point count, raster dimensions and cell count,
skeleton pixels, graph nodes and edges, connected components, pruned nodes,
extended endpoints, and centerline part count.

## Parameters

| option | default | effect |
|---|---:|---|
| `--footprint-width` | 20 m | width of the buffered point footprint |
| `--corridor-width` | 8 m | final corridor width |
| `--cell-size` | footprint / 16 | raster resolution; smaller is slower |
| `--min-branch-length` | 10 m | removes shorter leaf branches |
| `--extend-endpoints` | 0 m | extends graph leaves before buffering |
| `--max-cells` | 10,000,000 | rejects unexpectedly large rasters |

## Python API

```python
from track2corridor import CorridorOptions, CorridorResult, build_corridor

result: CorridorResult = build_corridor(
    points,
    "EPSG:32637",
    CorridorOptions(footprint_width=14, corridor_width=6, cell_size=1),
)
print(result.diagnostics.to_dict())
```

## Input behavior

- LAS/LAZ uses `gps_time` for stable ordering when that dimension exists.
- CSV uses source order unless `--time-field` is supplied.
- Other vector formats must contain only Point geometries and retain their CRS.
- An explicit `--crs` must match embedded CRS metadata; reprojection is never
  performed automatically.

## Limits

- Coordinates must use a projected CRS with horizontal units in metres.
- The method derives a skeleton from point buffers; it is not a map-matching or
  trajectory-inference algorithm.
- Disconnected point clusters produce multiple centerline components.
- Dense data, a very small cell size, or a very large extent can create expensive
  rasters; `--max-cells` provides a hard safety limit.
- Results should be visually reviewed when the footprint contains loops, wide
  junctions, or sparse gaps.

Run `track2corridor --help` for all options. Exit code `0` means success and `2`
means invalid input or a processing failure.

## Development

```bash
python -m pip install -e ".[test]"
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Copyright 2026 Alena Nikitina. Licensed under the [Apache License 2.0](https://github.com/NikitinaAD/track2corridor-geo/blob/main/LICENSE).
