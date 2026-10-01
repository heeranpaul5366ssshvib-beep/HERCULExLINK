"""Validated ARC grid parsing and small grid utilities."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Sequence, TypeAlias

Grid: TypeAlias = tuple[tuple[int, ...], ...]


def parse_grid(value: object) -> Grid:
    """Validate and freeze an ARC grid (nonempty, rectangular, colors 0..9)."""
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("grid must be a nonempty sequence of rows")
    rows: list[tuple[int, ...]] = []
    width: int | None = None
    for row in value:
        if not isinstance(row, (list, tuple)) or not row:
            raise ValueError("grid rows must be nonempty sequences")
        parsed: list[int] = []
        for cell in row:
            if isinstance(cell, bool) or not isinstance(cell, int) or not 0 <= cell <= 9:
                raise ValueError(f"invalid ARC color: {cell!r}")
            parsed.append(cell)
        if width is None:
            width = len(parsed)
        elif len(parsed) != width:
            raise ValueError("grid must be rectangular")
        rows.append(tuple(parsed))
    return tuple(rows)


def dimensions(grid: Grid) -> tuple[int, int]:
    return len(grid), len(grid[0])


def to_lists(grid: Grid) -> list[list[int]]:
    return [list(row) for row in grid]


def make_grid(height: int, width: int, fill: int = 0) -> Grid:
    if height < 1 or width < 1 or not 0 <= fill <= 9:
        raise ValueError("invalid grid dimensions or fill color")
    return tuple(tuple(fill for _ in range(width)) for _ in range(height))


def non_background_cells(grid: Grid, background: int = 0) -> frozenset[tuple[int, int]]:
    return frozenset((r, c) for r, row in enumerate(grid)
                     for c, value in enumerate(row) if value != background)


def colors(grid: Grid) -> frozenset[int]:
    return frozenset(value for row in grid for value in row)


def infer_background(grid: Grid) -> int:
    """Infer the background color as 0 if present, otherwise most frequent."""
    counts = Counter(value for row in grid for value in row)
    if 0 in counts:
        return 0
    maximum = max(counts.values())
    tied = [color for color, count in counts.items() if count == maximum]
    return min(tied)

