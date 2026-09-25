"""Generate and process all documented track2corridor scenarios."""

from __future__ import annotations

import json

import numpy as np
from make_example import OUTPUT
from make_example import main as make_example

from track2corridor import CorridorOptions, build_corridor
from track2corridor.io import read_track, write_result


def _run(name: str, filename: str, options: CorridorOptions) -> dict:
    points, crs = read_track(OUTPUT / filename, crs="EPSG:32637", time_field="sequence")
    result = build_corridor(points, crs, options)
    write_result(OUTPUT / f"{name}.gpkg", result)
    diagnostics = result.diagnostics.to_dict()
    (OUTPUT / f"{name}.json").write_text(
        json.dumps(diagnostics, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"{name:14} components={diagnostics['connected_components']} "
        f"parts={diagnostics['centerline_parts']} pruned={diagnostics['pruned_nodes']}"
    )
    return diagnostics


def main() -> None:
    make_example()
    standard = CorridorOptions(
        footprint_width=14,
        corridor_width=6,
        cell_size=1,
        min_branch_length=4,
    )
    summaries = {
        "mls_s_track": _run("mls-s-track", "mls-s-track.csv", standard),
        "disconnected": _run(
            "disconnected",
            "disconnected-track.csv",
            CorridorOptions(
                footprint_width=10,
                corridor_width=5,
                cell_size=1,
                min_branch_length=3,
            ),
        ),
        "short_spur": _run(
            "short-spur",
            "short-spur-track.csv",
            CorridorOptions(
                footprint_width=8,
                corridor_width=4,
                cell_size=0.75,
                min_branch_length=12,
            ),
        ),
    }
    if summaries["mls_s_track"]["connected_components"] != 1:
        raise AssertionError("the standard MLS example must produce one graph component")
    if summaries["disconnected"]["connected_components"] != 2:
        raise AssertionError("the disconnected example must produce two graph components")

    csv_points, _ = read_track(OUTPUT / "format-track.csv", crs="EPSG:32637", time_field="time")
    laz_points, _ = read_track(OUTPUT / "format-track.laz")
    vector_points, _ = read_track(OUTPUT / "format-track.gpkg", layer="track", time_field="time")
    if not (np.allclose(csv_points, laz_points) and np.allclose(csv_points, vector_points)):
        raise AssertionError("CSV, LAZ, and GeoPackage readers returned different ordered points")
    summaries["equivalent_input_formats"] = {
        "points": len(csv_points),
        "formats": ["CSV", "LAZ", "GeoPackage"],
        "same_ordered_coordinates": True,
    }
    (OUTPUT / "summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n",
        encoding="utf-8",
    )
    print("input formats  CSV=LAZ=GeoPackage (same ordered coordinates)")


if __name__ == "__main__":
    main()
