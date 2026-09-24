import geopandas as gpd
import laspy
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from track2corridor import CorridorOptions, build_corridor
from track2corridor.cli import main
from track2corridor.io import load_track


def test_straight_track_builds_valid_corridor():
    points = np.column_stack([np.linspace(0, 80, 81), np.zeros(81)])
    result = build_corridor(
        points,
        "EPSG:3857",
        CorridorOptions(footprint_width=12, corridor_width=6, cell_size=1, min_branch_length=3),
    )
    assert result.centerline.length > 60
    assert result.corridor.is_valid
    assert result.corridor.area > 300
    assert result.diagnostics.graph_edges > 0


def test_ring_is_traversed_without_leaf_nodes():
    angles = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    points = np.column_stack([30 * np.cos(angles), 30 * np.sin(angles)])
    result = build_corridor(
        points,
        "EPSG:3857",
        CorridorOptions(footprint_width=8, corridor_width=4, cell_size=1, min_branch_length=3),
    )
    assert result.centerline.length > 100
    assert result.diagnostics.skeleton_pixels == result.diagnostics.graph_nodes
    assert result.corridor.is_valid


def test_disconnected_clusters_produce_multiple_components():
    points = np.vstack(
        [
            np.column_stack([np.linspace(0, 20, 21), np.zeros(21)]),
            np.column_stack([np.linspace(80, 100, 21), np.zeros(21)]),
        ]
    )
    result = build_corridor(
        points,
        "EPSG:3857",
        CorridorOptions(footprint_width=10, corridor_width=4, cell_size=1),
    )
    assert result.diagnostics.connected_components == 2
    assert result.diagnostics.centerline_parts == 2


def test_invalid_crs_and_raster_limit_are_rejected():
    points = np.array([[0, 0], [100, 0]], dtype=float)
    for crs, options, message in [
        ("EPSG:4326", CorridorOptions(), "projected"),
        ("EPSG:3857", CorridorOptions(cell_size=0.01, max_cells=100), "max_cells"),
    ]:
        try:
            build_corridor(points, crs, options)
            raise AssertionError("invalid input was accepted")
        except ValueError as exc:
            assert message in str(exc)


def test_csv_las_and_vector_inputs_have_deterministic_order(tmp_path):
    csv_path = tmp_path / "track.csv"
    pd.DataFrame({"x": [20, 0, 10], "y": [2, 0, 1], "time": [3, 1, 2]}).to_csv(
        csv_path,
        index=False,
    )
    csv_points, csv_crs = load_track(csv_path, crs="EPSG:3857", time_field="time")
    assert csv_points[:, 0].tolist() == [0.0, 10.0, 20.0]
    assert csv_crs.to_epsg() == 3857

    las_path = tmp_path / "track.las"
    header = laspy.LasHeader(point_format=1, version="1.2")
    cloud = laspy.LasData(header)
    cloud.x = np.array([20.0, 0.0, 10.0])
    cloud.y = np.array([2.0, 0.0, 1.0])
    cloud.gps_time = np.array([3.0, 1.0, 2.0])
    cloud.write(las_path)
    las_points, _ = load_track(las_path, crs="EPSG:3857")
    assert las_points[:, 0].tolist() == [0.0, 10.0, 20.0]

    vector_path = tmp_path / "track.gpkg"
    gpd.GeoDataFrame(
        {"time": [2, 1]},
        geometry=[Point(10, 1), Point(0, 0)],
        crs="EPSG:3857",
    ).to_file(vector_path, layer="track", driver="GPKG", index=False)
    vector_points, vector_crs = load_track(vector_path, layer="track", time_field="time")
    assert vector_points[:, 0].tolist() == [0.0, 10.0]
    assert vector_crs.to_epsg() == 3857


def test_input_errors_are_explicit(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("east,north\n0,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="x and y"):
        load_track(bad_csv, crs="EPSG:3857")
    with pytest.raises(ValueError, match="N×2"):
        build_corridor([[0, 0]], "EPSG:3857")


def test_cli_writes_three_layers_and_diagnostics(tmp_path):
    source = tmp_path / "track.csv"
    output = tmp_path / "corridor.gpkg"
    diagnostics = tmp_path / "diagnostics.json"
    rows = ["x,y"] + [f"{value},0" for value in range(41)]
    source.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert (
        main(
            [
                "build",
                str(source),
                "--crs",
                "EPSG:3857",
                "--footprint-width",
                "10",
                "--corridor-width",
                "4",
                "--cell-size",
                "1",
                "--min-branch-length",
                "2",
                "--output",
                str(output),
                "--diagnostics",
                str(diagnostics),
            ]
        )
        == 0
    )
    for layer in ("footprint", "centerline", "corridor"):
        assert len(gpd.read_file(output, layer=layer)) == 1
    assert '"graph_edges"' in diagnostics.read_text(encoding="utf-8")
