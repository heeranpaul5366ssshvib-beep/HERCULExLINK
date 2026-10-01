"""Deterministic ARC grid and object transformation primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from .grid import Grid, make_grid, infer_background
from .objects import ArcObject, connected_components, describe_object, extract_objects


def reflect_horizontal(grid: Grid) -> Grid:
    return tuple(reversed(grid))


def reflect_vertical(grid: Grid) -> Grid:
    return tuple(tuple(reversed(row)) for row in grid)


def rotate(grid: Grid, quarter_turns: int = 1) -> Grid:
    """Rotate clockwise by an integer number of quarter turns."""
    turns = quarter_turns % 4
    result = grid
    for _ in range(turns):
        result = tuple(tuple(result[r][c] for r in range(len(result) - 1, -1, -1))
                       for c in range(len(result[0])))
    return result


def translate(grid: Grid, dy: int, dx: int, background: int = 0) -> Grid:
    h, w = len(grid), len(grid[0])
    out = [list(row) for row in make_grid(h, w, background)]
    for r, row in enumerate(grid):
        for c, value in enumerate(row):
            rr, cc = r + dy, c + dx
            if 0 <= rr < h and 0 <= cc < w:
                out[rr][cc] = value
    return tuple(tuple(row) for row in out)


def scale(grid: Grid, sy: int, sx: int | None = None) -> Grid:
    sx = sy if sx is None else sx
    if sy < 1 or sx < 1:
        raise ValueError("scale factors must be positive integers")
    return tuple(tuple(value for value in row for _ in range(sx))
                 for row in grid for _ in range(sy))


def tile(grid: Grid, ny: int, nx: int | None = None) -> Grid:
    nx = ny if nx is None else nx
    if ny < 1 or nx < 1:
        raise ValueError("tile counts must be positive integers")
    return tuple(tuple(grid[r % len(grid)][c % len(grid[0])]
                       for c in range(len(grid[0]) * nx))
                 for r in range(len(grid) * ny))


def crop(grid: Grid, top: int, left: int, bottom: int, right: int) -> Grid:
    if not (0 <= top < bottom <= len(grid) and 0 <= left < right <= len(grid[0])):
        raise ValueError("crop bounds are outside the grid or empty")
    return tuple(tuple(row[left:right]) for row in grid[top:bottom])


def crop_non_background(grid: Grid, background: int = 0) -> Grid:
    cells = [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row)
             if value != background]
    if not cells:
        return ((background,),)
    return crop(grid, min(r for r, _ in cells), min(c for _, c in cells),
                max(r for r, _ in cells) + 1, max(c for _, c in cells) + 1)


def crop_color(grid: Grid, color: int, background: int = 0) -> Grid:
    selected = tuple(tuple(value if value == color else background for value in row)
                     for row in grid)
    return crop_non_background(selected, background)


def fill_enclosed_background(grid: Grid, color: int | None = None,
                             background: int = 0) -> Grid:
    """Fill enclosed background cells with color or the most frequent foreground."""
    from .objects import enclosed_background_cells
    if color is None:
        counts = {value: sum(cell == value for row in grid for cell in row)
                  for value in {cell for row in grid for cell in row if cell != background}}
        if not counts:
            return grid
        color = min(counts, key=lambda value: (-counts[value], value))
    out = [list(row) for row in grid]
    for r, c in enclosed_background_cells(grid, background):
        out[r][c] = color
    return tuple(tuple(row) for row in out)


def object_bounding_boxes(grid: Grid, background: int = 0) -> Grid:
    out = [list(row) for row in grid]
    for obj in extract_objects(grid):
        top, left, bottom, right = obj.bbox
        for r in range(top, bottom):
            for c in range(left, right):
                if out[r][c] not in (background, obj.color):
                    raise ValueError("object bounding boxes of different colors overlap")
                out[r][c] = obj.color
    return tuple(tuple(row) for row in out)


def object_outlines(grid: Grid, background: int = 0) -> Grid:
    out = [[background] * len(grid[0]) for _ in grid]
    for obj in extract_objects(grid):
        for r, c in obj.cells:
            if any((r + dr, c + dc) not in obj.cells
                   for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1))):
                out[r][c] = obj.color
    return tuple(tuple(row) for row in out)


def object_shape_signature(obj: ArcObject) -> tuple:
    top, left, _, _ = obj.bbox
    return (obj.height, obj.width,
            tuple(sorted((r - top, c - left) for r, c in obj.cells)))


def object_feature(obj: ArcObject, feature: str) -> tuple | int | str:
    if feature == "size":
        return len(obj.cells)
    if feature == "shape":
        return object_shape_signature(obj)
    if feature == "orientation":
        return obj.orientation
    if feature == "symmetry":
        return obj.symmetry
    if feature == "dimensions":
        return obj.height, obj.width
    if feature == "aspect":
        return obj.height, obj.width
    if feature == "color":
        return obj.color
    raise ValueError(f"unknown object feature: {feature}")


def select_objects(grid: Grid, selector: str, background: int = 0) -> Grid:
    """Keep objects selected by a simple, explicitly named structural rule."""
    objects = extract_objects(grid)
    if not objects:
        return grid
    areas = [len(obj.cells) for obj in objects]
    if selector == "largest":
        chosen = {id(obj) for obj in objects if len(obj.cells) == max(areas)}
    elif selector == "smallest":
        chosen = {id(obj) for obj in objects if len(obj.cells) == min(areas)}
    elif selector == "unique-size":
        counts = {area: areas.count(area) for area in set(areas)}
        chosen = {id(obj) for obj in objects if counts[len(obj.cells)] == 1}
    elif selector == "unique-shape":
        shapes = [object_shape_signature(obj) for obj in objects]
        chosen = {id(obj) for obj, shape in zip(objects, shapes)
                  if shapes.count(shape) == 1}
    elif selector in {"most-frequent-color", "least-frequent-color"}:
        counts = {color: sum(obj.color == color for obj in objects)
                  for color in {obj.color for obj in objects}}
        target = (max(counts.values()) if selector == "most-frequent-color"
                  else min(counts.values()))
        colors = {color for color, value in counts.items() if value == target}
        chosen = {id(obj) for obj in objects if obj.color in colors}
    elif selector in {"symmetric", "asymmetric"}:
        chosen = {id(obj) for obj in objects
                  if any(obj.symmetry) == (selector == "symmetric")}
    elif selector in {"horizontal", "vertical", "square", "point", "wide", "tall"}:
        chosen = {id(obj) for obj in objects if obj.orientation == selector}
    else:
        raise ValueError(f"unknown object selector: {selector}")
    return render_objects((obj for obj in objects if id(obj) in chosen),
                          len(grid), len(grid[0]), background)


def recolor_objects_by_feature(grid: Grid, mapping: dict,
                               feature: str = "shape") -> Grid:
    """Recolor each whole component from a learned structural feature map."""
    out = [list(row) for row in grid]
    for obj in extract_objects(grid):
        color = mapping.get(object_feature(obj, feature), obj.color)
        if not isinstance(color, int) or not 0 <= color <= 9:
            raise ValueError("mapped object color is outside the ARC palette")
        for r, c in obj.cells:
            out[r][c] = color
    return tuple(tuple(row) for row in out)


def transform_each_object(grid: Grid, operation: str,
                          background: int = 0) -> Grid:
    """Apply a local geometric transform to every object at its top-left anchor."""
    transforms = {
        "reflect-horizontal": reflect_horizontal,
        "reflect-vertical": reflect_vertical,
        "rotate-90": lambda g: rotate(g, 1),
        "rotate-180": lambda g: rotate(g, 2),
        "rotate-270": lambda g: rotate(g, 3),
    }
    if operation not in transforms:
        raise ValueError(f"unknown local object transform: {operation}")
    out = [list(row) for row in make_grid(len(grid), len(grid[0]), background)]
    for obj in extract_objects(grid):
        top, left, bottom, right = obj.bbox
        local = tuple(tuple(grid[r][c] if (r, c) in obj.cells else background
                            for c in range(left, right))
                      for r in range(top, bottom))
        transformed = transforms[operation](local)
        if top + len(transformed) > len(grid) or left + len(transformed[0]) > len(grid[0]):
            raise ValueError("transformed object exceeds the grid boundary")
        for r, row in enumerate(transformed):
            for c, color in enumerate(row):
                if color == background:
                    continue
                rr, cc = top + r, left + c
                if out[rr][cc] not in (background, color):
                    raise ValueError("locally transformed objects collide")
                out[rr][cc] = color
    return tuple(tuple(row) for row in out)


def complete_symmetry(grid: Grid, axis: str = "vertical", background: int = 0) -> Grid:
    """Complete a grid under an axis reflection; incompatible halves are rejected."""
    h, w = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    for r in range(h):
        for c in range(w):
            if axis == "vertical":
                rr, cc = r, w - 1 - c
            elif axis == "horizontal":
                rr, cc = h - 1 - r, c
            elif axis == "diagonal":
                if h != w:
                    raise ValueError("diagonal symmetry requires a square grid")
                rr, cc = c, r
            elif axis == "antidiagonal":
                if h != w:
                    raise ValueError("antidiagonal symmetry requires a square grid")
                rr, cc = h - 1 - c, w - 1 - r
            else:
                raise ValueError(f"unknown symmetry axis: {axis}")
            a, b = grid[r][c], grid[rr][cc]
            if a != background and b != background and a != b:
                raise ValueError("input conflicts with the requested symmetry")
            out[r][c] = a if a != background else b
    return tuple(tuple(row) for row in out)


def gravity(grid: Grid, direction: str = "down", background: int = 0) -> Grid:
    """Move rigid monochrome objects until the edge or another object blocks them."""
    if direction not in {"up", "down", "left", "right"}:
        raise ValueError(f"unknown gravity direction: {direction}")
    vectors = {"up": (-1, 0), "down": (1, 0),
               "left": (0, -1), "right": (0, 1)}
    dr, dc = vectors[direction]
    if direction == "down":
        objects = sorted(extract_objects(grid), key=lambda o: -o.bbox[2])
    elif direction == "up":
        objects = sorted(extract_objects(grid), key=lambda o: o.bbox[0])
    elif direction == "right":
        objects = sorted(extract_objects(grid), key=lambda o: -o.bbox[3])
    else:
        objects = sorted(extract_objects(grid), key=lambda o: o.bbox[1])
    h, w = len(grid), len(grid[0])
    out = [[background] * w for _ in range(h)]
    for obj in objects:
        cells = obj.cells
        dy = dx = 0
        while True:
            shifted = {(r + dy + dr, c + dx + dc) for r, c in cells}
            if any(r < 0 or r >= h or c < 0 or c >= w for r, c in shifted):
                break
            if any(out[r][c] != background for r, c in shifted):
                break
            dy += dr
            dx += dc
        for r, c in cells:
            out[r + dy][c + dx] = obj.color
    return tuple(tuple(row) for row in out)


def connect_aligned_objects(grid: Grid, color_policy: str = "same",
                            background: int | None = None) -> Grid:
    """Fill gaps between row/column-aligned objects under a fixed color policy."""
    if color_policy not in {"same", "first", "second"}:
        raise ValueError(f"unknown connection color policy: {color_policy}")
    if background is None:
        background = infer_background(grid)
    objects = extract_objects(grid, background_color=background)
    out = [list(row) for row in grid]
    lines: dict[tuple[int, int], set[int]] = {}
    for i, first in enumerate(objects):
        for second in objects[i + 1:]:
            if color_policy == "same" and first.color != second.color:
                continue
            color = (first.color if color_policy in {"same", "first"}
                     else second.color)
            shared_rows = sorted({r for r, _ in first.cells} & {r for r, _ in second.cells})
            shared_cols = sorted({c for _, c in first.cells} & {c for _, c in second.cells})
            options = []
            for r in shared_rows:
                for ca in (c for rr, c in first.cells if rr == r):
                    for cb in (c for rr, c in second.cells if rr == r):
                        if abs(ca - cb) > 1:
                            options.append((abs(ca - cb) - 1, r,
                                            min(ca, cb), max(ca, cb), "horizontal"))
            for c in shared_cols:
                for ra in (r for r, cc in first.cells if cc == c):
                    for rb in (r for r, cc in second.cells if cc == c):
                        if abs(ra - rb) > 1:
                            options.append((abs(ra - rb) - 1, c,
                                            min(ra, rb), max(ra, rb), "vertical"))
            if not options:
                continue
            _, fixed, low, high, orientation = min(options)
            cells = (((fixed, p) for p in range(low + 1, high))
                     if orientation == "horizontal"
                     else ((p, fixed) for p in range(low + 1, high)))
            for point in cells:
                lines.setdefault(point, set()).add(color)
    for (r, c), colors in lines.items():
        if len(colors) > 1:
            raise ValueError("aligned connections assign conflicting colors")
        color = next(iter(colors))
        if out[r][c] not in (background, color):
            raise ValueError("aligned connection overwrites an object")
        out[r][c] = color
    return tuple(tuple(row) for row in out)


def connect_nearest_objects(grid: Grid, route: str = "horizontal-first",
                            color_policy: str = "same", background: int | None = None) -> Grid:
    """Connect the unique nearest object pair by one of two shortest L routes."""
    if route not in {"horizontal-first", "vertical-first"}:
        raise ValueError(f"unknown connection route: {route}")
    if color_policy not in {"same", "first", "second"}:
        raise ValueError(f"unknown connection color policy: {color_policy}")
    if background is None:
        background = infer_background(grid)
    objects = extract_objects(grid, background_color=background)
    options = []
    for i, first in enumerate(objects):
        for j in range(i + 1, len(objects)):
            second = objects[j]
            if color_policy == "same" and first.color != second.color:
                continue
            for a in first.cells:
                for b in second.cells:
                    distance = abs(a[0] - b[0]) + abs(a[1] - b[1])
                    options.append((distance, i, j, a, b))
    if not options:
        return grid
    minimum = min(option[0] for option in options)
    closest = [option for option in options if option[0] == minimum]
    object_pairs = {(option[1], option[2]) for option in closest}
    if len(object_pairs) != 1:
        raise ValueError("nearest object pair is ambiguous")
    if len(closest) != 1:
        raise ValueError("nearest endpoint correspondence is ambiguous")
    distance, first_index, second_index, first_cell, second_cell = closest[0]
    if distance <= 1:
        return grid
    first, second = objects[first_index], objects[second_index]
    color = (first.color if color_policy in {"same", "first"}
             else second.color)
    r1, c1 = first_cell
    r2, c2 = second_cell
    path = []
    if route == "horizontal-first":
        step = 1 if c2 > c1 else -1
        path.extend((r1, c) for c in range(c1 + step, c2 + step, step))
        step = 1 if r2 > r1 else -1
        path.extend((r, c2) for r in range(r1 + step, r2, step))
    else:
        step = 1 if r2 > r1 else -1
        path.extend((r, c1) for r in range(r1 + step, r2 + step, step))
        step = 1 if c2 > c1 else -1
        path.extend((r2, c) for c in range(c1 + step, c2, step))
    out = [list(row) for row in grid]
    for r, c in path:
        if out[r][c] != background:
            raise ValueError("nearest-object path crosses an occupied cell")
        out[r][c] = color
    return tuple(tuple(row) for row in out)


def extend_lines_to_edge(grid: Grid, background: int | None = None) -> Grid:
    """Extend every length-two-or-more monochrome row/column run to its edges."""
    if background is None:
        background = infer_background(grid)
    lines: dict[tuple[int, int], set[int]] = {}
    h, w = len(grid), len(grid[0])
    for r in range(h):
        start = 0
        while start < w:
            color = grid[r][start]
            end = start + 1
            while color != background and end < w and grid[r][end] == color:
                end += 1
            if color != background and end - start >= 2:
                for c in range(w):
                    lines.setdefault((r, c), set()).add(color)
            start = end
    for c in range(w):
        start = 0
        while start < h:
            color = grid[start][c]
            end = start + 1
            while color != background and end < h and grid[end][c] == color:
                end += 1
            if color != background and end - start >= 2:
                for r in range(h):
                    lines.setdefault((r, c), set()).add(color)
            start = end
    out = [list(row) for row in grid]
    for (r, c), colors in lines.items():
        if len(colors) > 1:
            raise ValueError("horizontal/vertical line extensions conflict")
        color = next(iter(colors))
        if out[r][c] not in (background, color):
            raise ValueError("line extension overwrites a different color")
        out[r][c] = color
    return tuple(tuple(row) for row in out)


def transform_objects_by_signature(
        grid: Grid, transforms: dict[tuple, tuple[int, int, int]]) -> Grid:
    """Apply inferred (dy, dx, output-color) rules keyed by color and shape."""
    from .objects import describe_object
    out_objects = []
    for component in connected_components(grid):
        top_left = min(component)
        color = grid[top_left[0]][top_left[1]]
        source = describe_object(color, component)
        key = (color, object_shape_signature(source))
        if key not in transforms:
            raise ValueError("no signature-matched transform for an input object")
        dy, dx, output_color = transforms[key]
        moved = {(r + dy, c + dx) for r, c in component}
        if any(not (0 <= r < len(grid) and 0 <= c < len(grid[0]))
               for r, c in moved):
            raise ValueError("signature-moved object exceeds grid bounds")
        out_objects.append(describe_object(output_color, moved))
    return render_objects(out_objects, len(grid), len(grid[0]))


def recolor(grid: Grid, mapping: dict[int, int]) -> Grid:
    if any(not (0 <= a <= 9 and 0 <= b <= 9) for a, b in mapping.items()):
        raise ValueError("colors must be between 0 and 9")
    return tuple(tuple(mapping.get(value, value) for value in row) for row in grid)


def recolor_by_palette_rank(grid: Grid, rank_mapping: dict[int, int],
                            measure: str = "cells") -> Grid:
    """Map each color's frequency/object-count rank to another input palette role."""
    palette = {value for row in grid for value in row}
    if measure == "cells":
        values = {color: sum(cell == color for row in grid for cell in row)
                  for color in palette}
    elif measure == "objects":
        from .objects import connected_components
        values = {color: (0 if color == 0 else
                          len(connected_components(grid, color=color)))
                  for color in palette}
    else:
        raise ValueError(f"unknown palette rank measure: {measure}")
    ordered = sorted(palette, key=lambda color: (-values[color], color))
    rank_to_color = {rank: color for rank, color in enumerate(ordered)}
    output_map = {color: rank_to_color.get(rank_mapping.get(rank, rank), color)
                  for rank, color in enumerate(ordered)}
    return recolor(grid, output_map)


def intersect(a: Grid, b: Grid, background: int = 0) -> Grid:
    if (len(a), len(a[0])) != (len(b), len(b[0])):
        raise ValueError("intersection requires equal dimensions")
    return tuple(tuple(x if x == y and x != background else background
                       for x, y in zip(ra, rb)) for ra, rb in zip(a, b))


def subtract(a: Grid, b: Grid, background: int = 0) -> Grid:
    if (len(a), len(a[0])) != (len(b), len(b[0])):
        raise ValueError("subtraction requires equal dimensions")
    return tuple(tuple(x if y == background else background
                       for x, y in zip(ra, rb)) for ra, rb in zip(a, b))


def overlay(base: Grid, foreground: Grid, background: int = 0) -> Grid:
    if (len(base), len(base[0])) != (len(foreground), len(foreground[0])):
        raise ValueError("overlay requires equal dimensions")
    return tuple(tuple(y if y != background else x for x, y in zip(ra, rb))
                 for ra, rb in zip(base, foreground))


def mask(grid: Grid, mask_grid: Grid, background: int = 0) -> Grid:
    if (len(grid), len(grid[0])) != (len(mask_grid), len(mask_grid[0])):
        raise ValueError("mask requires equal dimensions")
    return tuple(tuple(x if m != background else background
                       for x, m in zip(ra, rb)) for ra, rb in zip(grid, mask_grid))


def split_on_separator(grid: Grid, axis: str) -> tuple[Grid, ...]:
    """Split on complete, solid non-background rows or columns."""
    if axis == "horizontal":
        dividers = [r for r, row in enumerate(grid)
                    if row[0] != 0 and all(value == row[0] for value in row)]
        segments = []
        start = 0
        for divider in dividers:
            if divider > start:
                segments.append(tuple(grid[start:divider]))
            start = divider + 1
        if start < len(grid):
            segments.append(tuple(grid[start:]))
        return tuple(segments) if dividers else ()
    if axis == "vertical":
        width = len(grid[0])
        dividers = [c for c in range(width)
                    if grid[0][c] != 0 and all(row[c] == grid[0][c] for row in grid)]
        segments = []
        start = 0
        for divider in dividers:
            if divider > start:
                segments.append(tuple(tuple(row[start:divider]) for row in grid))
            start = divider + 1
        if start < width:
            segments.append(tuple(tuple(row[start:]) for row in grid))
        return tuple(segments) if dividers else ()
    raise ValueError("separator axis must be horizontal or vertical")


def combine_regions(a: Grid, b: Grid, operation: str,
                    background: int = 0) -> Grid:
    if (len(a), len(a[0])) != (len(b), len(b[0])):
        raise ValueError("region combination requires equal dimensions")
    out = []
    for row_a, row_b in zip(a, b):
        row = []
        for x, y in zip(row_a, row_b):
            if operation == "union":
                if x != background and y != background and x != y:
                    raise ValueError("overlapping regions contain different colors")
                row.append(x if x != background else y)
            elif operation == "intersection":
                row.append(x if x == y and x != background else background)
            elif operation == "xor":
                if x != background and y != background and x != y:
                    raise ValueError("xor overlap contains different colors")
                row.append(background if x != background and y != background
                           else x if x != background else y)
            elif operation == "subtract-left":
                row.append(x if y == background else background)
            elif operation == "subtract-right":
                row.append(y if x == background else background)
            else:
                raise ValueError(f"unknown region operation: {operation}")
        out.append(tuple(row))
    return tuple(out)


def count(grid: Grid, mode: str = "cells", color: int | None = None) -> int:
    if mode == "cells":
        return sum(1 for row in grid for value in row
                   if value != 0 and (color is None or value == color))
    if mode == "objects":
        return sum(1 for component in connected_components(grid)
                   if color is None or grid[min(component)[0]][min(component)[1]] == color)
    if mode == "colors":
        return len({value for row in grid for value in row if value != 0
                    and (color is None or value == color)})
    if mode == "color_cells":
        if color is None:
            raise ValueError("color_cells mode requires color")
        return sum(value == color for row in grid for value in row)
    raise ValueError(f"unknown count mode: {mode}")


def order_objects(objects: Iterable[ArcObject], key: str = "top_left",
                  reverse: bool = False) -> tuple[ArcObject, ...]:
    keys: dict[str, Callable[[ArcObject], Any]] = {
        "top_left": lambda o: (o.bbox[0], o.bbox[1]),
        "area": lambda o: len(o.cells), "color": lambda o: o.color,
        "width": lambda o: o.width, "height": lambda o: o.height,
        "centroid": lambda o: o.centroid,
    }
    if key not in keys:
        raise ValueError(f"unknown object ordering key: {key}")
    return tuple(sorted(objects, key=keys[key], reverse=reverse))


def render_objects(objects: Iterable[ArcObject], height: int, width: int,
                   background: int = 0) -> Grid:
    out = [list(row) for row in make_grid(height, width, background)]
    for obj in objects:
        for r, c in sorted(obj.cells):
            if 0 <= r < height and 0 <= c < width:
                out[r][c] = obj.color
    return tuple(tuple(row) for row in out)


def move_objects(grid: Grid, dy: int, dx: int, background: int = 0) -> Grid:
    objects = []
    for component in connected_components(grid):
        r, c = min(component)
        objects.append(describe_object(grid[r][c],
                                       ((rr + dy, cc + dx) for rr, cc in component)))
    return render_objects(objects, len(grid), len(grid[0]), background)


def grow(grid: Grid, iterations: int = 1, connectivity: int = 4) -> Grid:
    if iterations < 0 or connectivity not in (4, 8):
        raise ValueError("iterations must be nonnegative and connectivity 4 or 8")
    current = [list(row) for row in grid]
    h, w = len(grid), len(grid[0])
    offsets = [(r, c) for r in (-1, 0, 1) for c in (-1, 0, 1)
               if (r or c) and (connectivity == 8 or abs(r) + abs(c) == 1)]
    for _ in range(iterations):
        additions: dict[tuple[int, int], set[int]] = {}
        for r in range(h):
            for c in range(w):
                color = current[r][c]
                if color == 0:
                    continue
                for dr, dc in offsets:
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < h and 0 <= cc < w and current[rr][cc] == 0:
                        additions.setdefault((rr, cc), set()).add(color)
        for (r, c), candidates in additions.items():
            if len(candidates) == 1:
                current[r][c] = next(iter(candidates))
    return tuple(tuple(row) for row in current)


def split_object(grid: Grid, connectivity: int = 4) -> tuple[ArcObject, ...]:
    return tuple(describe_object(grid[min(cells)[0]][min(cells)[1]], cells)
                 for cells in connected_components(grid, connectivity=connectivity))


def merge_objects(objects: Iterable[ArcObject], height: int, width: int,
                  background: int = 0) -> Grid:
    return render_objects(objects, height, width, background)


def relative_position(a: ArcObject, b: ArcObject) -> str:
    from .objects import relative_position as _relative_position
    return _relative_position(a, b)


def coordinate_transform(point: tuple[int, int], height: int, width: int,
                         operation: str) -> tuple[int, int, int, int]:
    """Map a cell coordinate and return (row, column, out_height, out_width)."""
    r, c = point
    if not (0 <= r < height and 0 <= c < width):
        raise ValueError("point is outside the source grid")
    if operation == "identity":
        return r, c, height, width
    if operation == "reflect_horizontal":
        return height - 1 - r, c, height, width
    if operation == "reflect_vertical":
        return r, width - 1 - c, height, width
    if operation == "rotate90":
        return c, height - 1 - r, width, height
    if operation == "rotate180":
        return height - 1 - r, width - 1 - c, height, width
    if operation == "rotate270":
        return width - 1 - c, r, width, height
    raise ValueError(f"unknown coordinate transform: {operation}")


def complete_pattern(grid: Sequence[Sequence[int | None]]) -> tuple[tuple[int, ...], ...]:
    """Fill None cells using the shortest row period consistent with known cells."""
    if not grid or not grid[0] or any(len(row) != len(grid[0]) for row in grid):
        raise ValueError("pattern must be a nonempty rectangle")
    result = []
    for row in grid:
        width = len(row)
        period = next((p for p in range(1, width + 1)
                       if all(row[i] is None or row[j] is None or row[i] == row[j]
                              for i in range(width) for j in range(width)
                              if i % p == j % p)), None)
        if period is None:
            raise ValueError("no periodic completion is consistent with known cells")
        values: list[int | None] = [None] * period
        for i, value in enumerate(row):
            if value is not None:
                slot = i % period
                if values[slot] is not None and values[slot] != value:
                    raise ValueError("inconsistent periodic row")
                values[slot] = value
        if any(value is None for value in values):
            raise ValueError("insufficient known cells to infer the row period")
        result.append(tuple(int(values[i % period]) for i in range(width)))
    return tuple(result)
