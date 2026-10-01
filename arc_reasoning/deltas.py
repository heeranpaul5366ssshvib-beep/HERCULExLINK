"""Pixel-level input/output change representation for ARC demonstrations."""

from __future__ import annotations

from dataclasses import dataclass

from .grid import Grid, dimensions


Cell = tuple[int, int, int]
RecoloredCell = tuple[int, int, int, int]


@dataclass(frozen=True)
class GridDelta:
    source_dimensions: tuple[int, int]
    target_dimensions: tuple[int, int]
    preserved_cells: frozenset[Cell]
    removed_cells: frozenset[Cell]
    added_cells: frozenset[Cell]
    recolored_cells: frozenset[RecoloredCell]

    @property
    def dimensions_changed(self) -> bool:
        return self.source_dimensions != self.target_dimensions

    @property
    def changed_cell_count(self) -> int:
        return (len(self.removed_cells) + len(self.added_cells) +
                len(self.recolored_cells))


def compare_grids(source: Grid, target: Grid, background: int = 0) -> GridDelta:
    """Classify cells as preserved, removed, added, or recolored.

    Objects that move appear as removals and additions at pixel level. Higher
    reasoning layers can use object signatures to infer that correspondence.
    """
    source_h, source_w = dimensions(source)
    target_h, target_w = dimensions(target)
    preserved: set[Cell] = set()
    removed: set[Cell] = set()
    added: set[Cell] = set()
    recolored: set[RecoloredCell] = set()
    for row in range(max(source_h, target_h)):
        for col in range(max(source_w, target_w)):
            old = source[row][col] if row < source_h and col < source_w else background
            new = target[row][col] if row < target_h and col < target_w else background
            if old == new:
                continue
            if old == background:
                added.add((row, col, new))
            elif new == background:
                removed.add((row, col, old))
            else:
                recolored.add((row, col, old, new))
    for row in range(min(source_h, target_h)):
        for col in range(min(source_w, target_w)):
            value = source[row][col]
            if value != background and target[row][col] == value:
                preserved.add((row, col, value))
    return GridDelta((source_h, source_w), (target_h, target_w),
                     frozenset(preserved), frozenset(removed),
                     frozenset(added), frozenset(recolored))
