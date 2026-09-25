"""Create deterministic synthetic mobile-mapping trajectory examples."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import laspy
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import Point

ROOT = Path(__file__).parent
OUTPUT = ROOT / "generated"


def _write_csv(name: str, points: np.ndarray) -> None:
    pd.DataFrame({"x": points[:, 0], "y": points[:, 1], "sequence": np.arange(len(points))}).to_csv(
        OUTPUT / name, index=False
    )


def _write_format_examples(points: np.ndarray) -> None:
    times = np.arange(len(points), dtype=float)
    order = np.r_[np.arange(0, len(points), 2), np.arange(1, len(points), 2)]

    pd.DataFrame({"x": points[order, 0], "y": points[order, 1], "time": times[order]}).to_csv(
        OUTPUT / "format-track.csv", index=False
    )

    header = laspy.LasHeader(point_format=1, version="1.2")
    header.scales = np.array([0.01, 0.01, 0.01])
    header.add_crs(CRS.from_epsg(32637))
    cloud = laspy.LasData(header)
    cloud.x = points[order, 0]
    cloud.y = points[order, 1]
    cloud.z = np.zeros(len(points))
    cloud.gps_time = times[order]
    cloud.write(OUTPUT / "format-track.laz")

    gpd.GeoDataFrame(
        {"time": times[order]},
        geometry=[Point(x, y) for x, y in points[order]],
        crs="EPSG:32637",
    ).to_file(OUTPUT / "format-track.gpkg", layer="track", driver="GPKG", index=False)


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(42)

    # "Noise" here is reproducible positional scatter around a smooth MLS trajectory.
    x = np.linspace(0, 120, 121)
    y = 10 * np.sin(x / 22) + rng.normal(0, 0.8, len(x))
    mls_track = np.column_stack([x, y])
    _write_csv("mls-s-track.csv", mls_track)

    left = np.column_stack([np.linspace(0, 35, 36), rng.normal(0, 0.25, 36)])
    right = np.column_stack([np.linspace(75, 110, 36), rng.normal(0, 0.25, 36)])
    _write_csv("disconnected-track.csv", np.vstack([left, right]))

    main_line = np.column_stack([np.linspace(0, 80, 81), rng.normal(0, 0.2, 81)])
    side_spur = np.column_stack([np.full(8, 40.0), np.linspace(1, 8, 8)])
    _write_csv("short-spur-track.csv", np.vstack([main_line, side_spur]))

    # LAS quantizes coordinates to its declared scale, so use the same 0.01 m
    # representation for every format in this equivalence example.
    _write_format_examples(np.round(mls_track[:31], 2))
    print(f"Wrote synthetic mobile-mapping examples to {OUTPUT}")


if __name__ == "__main__":
    main()
