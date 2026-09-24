from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import laspy
import numpy as np
import pandas as pd
from pyproj import CRS


def read_track(path: str | Path, *, layer=None, crs=None, time_field=None):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".las", ".laz"}:
        with laspy.open(path) as reader:
            cloud = reader.read()
            source_crs = reader.header.parse_crs()
        order = (
            np.argsort(np.asarray(cloud.gps_time), kind="stable")
            if "gps_time" in cloud.point_format.dimension_names
            else slice(None)
        )
        points = np.column_stack([np.asarray(cloud.x)[order], np.asarray(cloud.y)[order]])
    elif suffix == ".csv":
        table = pd.read_csv(path)
        if not {"x", "y"}.issubset(table.columns):
            raise ValueError("CSV input must contain x and y columns")
        if time_field:
            if time_field not in table.columns:
                raise ValueError(f"Time field not found: {time_field}")
            table = table.sort_values(time_field, kind="stable")
        points = table[["x", "y"]].to_numpy(dtype=float)
        source_crs = CRS(crs) if crs else None
    else:
        frame = gpd.read_file(path, layer=layer)
        if frame.empty or not frame.geom_type.eq("Point").all():
            raise ValueError("Vector input must contain Point geometries")
        if time_field:
            if time_field not in frame.columns:
                raise ValueError(f"Time field not found: {time_field}")
            frame = frame.sort_values(time_field, kind="stable")
        points = np.column_stack([frame.geometry.x, frame.geometry.y])
        source_crs = frame.crs
    if crs:
        explicit = CRS(crs)
        if source_crs is not None and not explicit.equals(CRS(source_crs)):
            raise ValueError("Explicit CRS differs from the input CRS; reprojection is not automatic")
        source_crs = explicit
    return points, source_crs


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
        frame.to_file(temporary, layer=layer, driver="GPKG", index=False, mode="w" if index == 0 else "a")
    temporary.replace(path)

