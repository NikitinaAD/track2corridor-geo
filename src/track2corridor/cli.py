from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import CorridorOptions, build_corridor
from .io import read_track, write_result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="track2corridor",
        description="Build an auditable centerline and corridor from point tracks.",
    )
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("input", type=Path)
    build.add_argument("--layer")
    build.add_argument("--crs", help="required for CSV or data without CRS, e.g. EPSG:32637")
    build.add_argument("--time-field")
    build.add_argument("--footprint-width", type=float, default=20.0)
    build.add_argument("--corridor-width", type=float, default=8.0)
    build.add_argument("--cell-size", type=float)
    build.add_argument("--min-branch-length", type=float, default=10.0)
    build.add_argument("--extend-endpoints", type=float, default=0.0)
    build.add_argument("--max-cells", type=int, default=10_000_000)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--diagnostics", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        points, crs = read_track(
            args.input, layer=args.layer, crs=args.crs, time_field=args.time_field
        )
        options = CorridorOptions(
            footprint_width=args.footprint_width,
            corridor_width=args.corridor_width,
            cell_size=args.cell_size,
            min_branch_length=args.min_branch_length,
            extend_endpoints=args.extend_endpoints,
            max_cells=args.max_cells,
        )
        result = build_corridor(points, crs, options)
        write_result(args.output, result)
        diagnostics = args.diagnostics or args.output.with_suffix(".json")
        diagnostics.parent.mkdir(parents=True, exist_ok=True)
        temporary = diagnostics.with_suffix(diagnostics.suffix + ".tmp")
        temporary.write_text(
            json.dumps(result.diagnostics.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(diagnostics)
        print(
            f"Built {result.diagnostics.centerline_parts} centerline part(s) from "
            f"{result.diagnostics.input_points} input points"
        )
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"track2corridor: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

