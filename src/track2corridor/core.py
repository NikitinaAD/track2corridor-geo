from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import networkx as nx
import numpy as np
from pyproj import CRS
from shapely import buffer, line_merge, union_all
from shapely import points as make_points
from shapely.geometry import LineString
from skimage.draw import disk
from skimage.morphology import skeletonize


@dataclass(frozen=True)
class CorridorOptions:
    footprint_width: float = 20.0
    corridor_width: float = 8.0
    cell_size: float | None = None
    min_branch_length: float = 10.0
    extend_endpoints: float = 0.0
    max_cells: int = 10_000_000


@dataclass(frozen=True)
class CorridorDiagnostics:
    input_points: int
    cell_size: float
    raster_rows: int
    raster_columns: int
    raster_cells: int
    skeleton_pixels: int
    graph_nodes: int
    graph_edges: int
    connected_components: int
    pruned_nodes: int
    extended_endpoints: int
    centerline_parts: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CorridorResult:
    footprint: object
    centerline: object
    corridor: object
    crs: CRS
    diagnostics: CorridorDiagnostics


def _metric_crs(value) -> CRS:
    if value is None:
        raise ValueError("A projected CRS is required")
    crs = CRS(value)
    if not crs.is_projected:
        raise ValueError("CRS must be projected")
    axes = crs.axis_info[:2]
    if len(axes) < 2 or any(abs(axis.unit_conversion_factor - 1.0) > 1e-9 for axis in axes):
        raise ValueError("CRS horizontal units must be metres")
    return crs


def _validate_options(options: CorridorOptions) -> float:
    numeric = {
        "footprint_width": options.footprint_width,
        "corridor_width": options.corridor_width,
        "min_branch_length": options.min_branch_length,
        "extend_endpoints": options.extend_endpoints,
    }
    if any(not math.isfinite(value) or value < 0 for value in numeric.values()):
        raise ValueError(
            "Widths, branch length and endpoint extension must be finite and non-negative"
        )
    if options.footprint_width <= 0 or options.corridor_width <= 0:
        raise ValueError("Footprint and corridor widths must be positive")
    cell_size = options.cell_size or options.footprint_width / 16.0
    if not math.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("cell_size must be positive")
    if options.max_cells <= 0:
        raise ValueError("max_cells must be positive")
    return cell_size


def _pixel_graph(mask: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> nx.Graph:
    graph = nx.Graph()
    pixels = {tuple(position) for position in np.argwhere(mask)}
    for row, column in pixels:
        node = (int(row), int(column))
        graph.add_node(node, position=(float(xs[column]), float(ys[row])))
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for row, column in pixels:
        node = (int(row), int(column))
        x1, y1 = graph.nodes[node]["position"]
        for dr, dc in offsets:
            neighbor = (row + dr, column + dc)
            if neighbor not in pixels or node >= neighbor:
                continue
            x2, y2 = graph.nodes[neighbor]["position"]
            graph.add_edge(node, neighbor, length=math.hypot(x2 - x1, y2 - y1))
    return graph


def _leaf_branch(graph: nx.Graph, leaf) -> tuple[list, float, object]:
    path = [leaf]
    length = 0.0
    previous = None
    current = leaf
    while True:
        onward = [node for node in graph.neighbors(current) if node != previous]
        if not onward:
            return path, length, current
        neighbor = onward[0]
        length += float(graph.edges[current, neighbor]["length"])
        previous, current = current, neighbor
        if graph.degree(current) != 2:
            return path, length, current
        path.append(current)


def _prune_short_leaf_branches(graph: nx.Graph, threshold: float) -> int:
    if threshold <= 0:
        return 0
    removed = 0
    while True:
        scheduled = set()
        for leaf in [node for node, degree in graph.degree if degree == 1]:
            path, length, endpoint = _leaf_branch(graph, leaf)
            if graph.degree(endpoint) >= 3 and length < threshold:
                scheduled.update(path)
        if not scheduled:
            return removed
        graph.remove_nodes_from(scheduled)
        removed += len(scheduled)


def _extend_leaves(graph: nx.Graph, distance: float) -> int:
    if distance <= 0:
        return 0
    updates = {}
    for node, degree in graph.degree:
        if degree != 1:
            continue
        neighbor = next(iter(graph.neighbors(node)))
        x, y = graph.nodes[node]["position"]
        nx_, ny_ = graph.nodes[neighbor]["position"]
        dx, dy = x - nx_, y - ny_
        length = math.hypot(dx, dy)
        if length:
            updates[node] = (x + distance * dx / length, y + distance * dy / length)
    nx.set_node_attributes(graph, updates, "position")
    return len(updates)


def _centerline(graph: nx.Graph):
    edges = [
        LineString([graph.nodes[left]["position"], graph.nodes[right]["position"]])
        for left, right in graph.edges
    ]
    if not edges:
        raise ValueError("Skeleton contains no connected line segments")
    return line_merge(union_all(edges))


def build_corridor(points, crs, options: CorridorOptions | None = None) -> CorridorResult:
    """Build a raster-skeleton centerline and a fixed-width corridor."""
    options = options or CorridorOptions()
    cell_size = _validate_options(options)
    output_crs = _metric_crs(crs)
    coordinates = np.asarray(points, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[1] != 2 or len(coordinates) < 2:
        raise ValueError("points must be an N×2 array with at least two rows")
    if not np.isfinite(coordinates).all():
        raise ValueError("points contain non-finite coordinates")

    radius = options.footprint_width / 2.0
    point_buffers = buffer(make_points(coordinates), radius, quad_segs=8)
    footprint = union_all(point_buffers)
    minimum = coordinates.min(axis=0) - radius
    maximum = coordinates.max(axis=0) + radius
    minx, miny = minimum
    maxx, maxy = maximum
    columns = int(math.ceil((maxx - minx) / cell_size)) + 1
    rows = int(math.ceil((maxy - miny) / cell_size)) + 1
    cells = rows * columns
    if cells > options.max_cells:
        raise ValueError(
            f"Raster would contain {cells:,} cells, above max_cells={options.max_cells:,}"
        )
    xs = minx + np.arange(columns) * cell_size
    ys = maxy - np.arange(rows) * cell_size
    mask = np.zeros((rows, columns), dtype=bool)
    pixel_radius = radius / cell_size
    for x, y in coordinates:
        center = ((maxy - y) / cell_size, (x - minx) / cell_size)
        rr, cc = disk(center, pixel_radius, shape=mask.shape)
        mask[rr, cc] = True
    skeleton = skeletonize(mask)
    graph = _pixel_graph(skeleton, xs, ys)
    if graph.number_of_edges() == 0:
        raise ValueError("Unable to derive a connected centerline from the input points")
    pruned = _prune_short_leaf_branches(graph, options.min_branch_length)
    extended = _extend_leaves(graph, options.extend_endpoints)
    centerline = _centerline(graph)
    corridor = centerline.buffer(options.corridor_width / 2.0, cap_style=2, join_style=1)
    parts = len(centerline.geoms) if hasattr(centerline, "geoms") else 1
    diagnostics = CorridorDiagnostics(
        input_points=len(coordinates),
        cell_size=float(cell_size),
        raster_rows=rows,
        raster_columns=columns,
        raster_cells=cells,
        skeleton_pixels=int(np.count_nonzero(skeleton)),
        graph_nodes=graph.number_of_nodes(),
        graph_edges=graph.number_of_edges(),
        connected_components=nx.number_connected_components(graph),
        pruned_nodes=pruned,
        extended_endpoints=extended,
        centerline_parts=parts,
    )
    return CorridorResult(footprint, centerline, corridor, output_crs, diagnostics)
