import numpy as np
import geopandas as gpd

from track2corridor import CorridorOptions, build_corridor
from track2corridor.cli import main


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


def test_cli_writes_three_layers_and_diagnostics(tmp_path):
    source = tmp_path / "track.csv"
    output = tmp_path / "corridor.gpkg"
    diagnostics = tmp_path / "diagnostics.json"
    rows = ["x,y"] + [f"{value},0" for value in range(41)]
    source.write_text("\n".join(rows) + "\n", encoding="utf-8")
    assert main([
        "build", str(source), "--crs", "EPSG:3857", "--footprint-width", "10",
        "--corridor-width", "4", "--cell-size", "1", "--min-branch-length", "2",
        "--output", str(output), "--diagnostics", str(diagnostics),
    ]) == 0
    for layer in ("footprint", "centerline", "corridor"):
        assert len(gpd.read_file(output, layer=layer)) == 1
    assert '"graph_edges"' in diagnostics.read_text(encoding="utf-8")
