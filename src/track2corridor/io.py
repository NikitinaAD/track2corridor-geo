from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import laspy
import numpy as np
import pandas as pd
from pyproj import CRS


def _xy(table, *, time_field=None) -> np.ndarray:
    if time_field:
        if time_field not in table.columns:
            raise ValueError(f"Time field not found: {time_field}")
        table = table.sort_values(time_field, kind="stable")
    return table[["x", "y"]].to_numpy(dtype=float)


def _load_csv(path: Path, *, time_field=None):
    table = pd.read_csv(path)
    if not {"x", "y"}.issubset(table.columns):
        raise ValueError("CSV input must contain x and y columns")
    return _xy(table, time_field=time_field), None


def _load_vector(path: Path, *, layer=None, time_field=None):
    frame = gpd.read_file(path, layer=layer)
    if frame.empty or not frame.geometry.geom_type.eq("Point").all():
        raise ValueError("Vector input must contain Point geometries")
    table = frame.drop(columns=frame.geometry.name).copy()
    table["x"] = frame.geometry.x
    table["y"] = frame.geometry.y
    return _xy(table, time_field=time_field), frame.crs


def _load_lidar(path: Path):
    with laspy.open(path) as stream:
        points = stream.read()
        embedded_crs = stream.header.parse_crs()
    coordinates = np.column_stack((np.asarray(points.x), np.asarray(points.y)))
    if "gps_time" in points.point_format.dimension_names:
        order = np.argsort(np.asarray(points.gps_time), kind="stable")
        coordinates = coordinates[order]
    return coordinates, embedded_crs


def load_track(path: str | Path, *, layer=None, crs=None, time_field=None):
    """Load ordered XY coordinates without performing reprojection."""
    source = Path(path)
    if source.suffix.lower() in {".las", ".laz"}:
        coordinates, embedded_crs = _load_lidar(source)
    elif source.suffix.lower() == ".csv":
        coordinates, embedded_crs = _load_csv(source, time_field=time_field)
    else:
        coordinates, embedded_crs = _load_vector(
            source,
            layer=layer,
            time_field=time_field,
        )

    if crs is None:
        return coordinates, embedded_crs
    declared_crs = CRS(crs)
    if embedded_crs is not None and not declared_crs.equals(CRS(embedded_crs)):
        raise ValueError("Explicit CRS differs from the input CRS; reprojection is not automatic")
    return coordinates, declared_crs


def write_result(path: str | Path, result) -> None:
    path = Path(path)
    if path.suffix.lower() != ".gpkg":
        raise ValueError("Output must be a .gpkg file because three layers are written")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.gpkg")
    if temporary.exists():
        temporary.unlink()
    layers = [
        ("footprint", result.footprint),
        ("centerline", result.centerline),
        ("corridor", result.corridor),
    ]
    for index, (layer, geometry) in enumerate(layers):
        frame = gpd.GeoDataFrame({"kind": [layer]}, geometry=[geometry], crs=result.crs)
        frame.to_file(
            temporary,
            layer=layer,
            driver="GPKG",
            index=False,
            mode="w" if index == 0 else "a",
        )
    temporary.replace(path)
