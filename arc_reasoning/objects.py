"""Symbolic objects, connected components, and spatial relations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Literal

from .grid import Grid

Point = tuple[int, int]
Connectivity = Literal[4, 8]


@dataclass(frozen=True)
class ArcObject:
    color: int
    cells: frozenset[Point]
    bbox: tuple[int, int, int, int]  # top, left, bottom, right (exclusive)
    width: int
    height: int
    centroid: tuple[float, float]
    symmetry: tuple[bool, bool, bool]  # horizontal, vertical, 180 degrees
    orientation: str
    # Enhanced invariant features
    perimeter: int = 0
    hole_count: int = 0
    touches_border: bool = False
    touches_corner: bool = False
    enclosed_by: frozenset[int] = field(default_factory=frozenset)  # colors of enclosing objects
    contains_colors: frozenset[int] = field(default_factory=frozenset)  # colors of contained objects
    adjacent_colors: frozenset[int] = field(default_factory=frozenset)  # colors of adjacent objects
    nearest_neighbor_dist: float = float('inf')
    nearest_neighbor_color: int | None = None
    alignment_signature: tuple = field(default_factory=tuple)  # alignment with other objects
    density: float = 0.0  # area / bbox_area
    compactness: float = 0.0  # perimeter^2 / area (normalized)
    # Relational signature fields
    left_of_colors: frozenset[int] = field(default_factory=frozenset)
    right_of_colors: frozenset[int] = field(default_factory=frozenset)
    above_colors: frozenset[int] = field(default_factory=frozenset)
    below_colors: frozenset[int] = field(default_factory=frozenset)
    same_row_colors: frozenset[int] = field(default_factory=frozenset)
    same_column_colors: frozenset[int] = field(default_factory=frozenset)
    between_pairs: frozenset[tuple[int, int]] = field(default_factory=frozenset)  # (color_a, color_b) where this is between them
    nearest_to_color: int | None = None
    farthest_from_color: int | None = None
    nth_from_left: int | None = None
    nth_from_right: int | None = None
    nth_from_top: int | None = None
    nth_from_bottom: int | None = None
    distance_to_colors: frozenset[tuple[int, float]] = field(default_factory=frozenset)  # (color, manhattan_distance)
    closest_corner: str | None = None  # "top_left", "top_right", "bottom_left", "bottom_right"
    closest_edge: str | None = None  # "top", "bottom", "left", "right"
    relative_signature: tuple = field(default_factory=tuple)  # normalized relational signature


def _neighbors(point: Point, connectivity: Connectivity) -> Iterable[Point]:
    r, c = point
    yield r - 1, c
    yield r + 1, c
    yield r, c - 1
    yield r, c + 1
    if connectivity == 8:
        yield r - 1, c - 1
        yield r - 1, c + 1
        yield r + 1, c - 1
        yield r + 1, c + 1


def _is_enclosed_by_object(grid: Grid, obj_cells: frozenset[Point], 
                           start: Point, background: int) -> bool:
    """Check if a background cell is enclosed by the object."""
    h, w = len(grid), len(grid[0])
    queue = deque([start])
    seen = {start}
    while queue:
        r, c = queue.popleft()
        # If we reach border, not enclosed
        if r == 0 or r == h - 1 or c == 0 or c == w - 1:
            return False
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in seen:
                if grid[nr][nc] == background and (nr, nc) not in obj_cells:
                    seen.add((nr, nc))
                    queue.append((nr, nc))
    return True


def connected_components(grid: Grid, color: int | None = None,
                         connectivity: Connectivity = 4,
                         include_background: bool = False,
                         background_color: int = 0) -> list[frozenset[Point]]:
    """Return same-color 4/8-connected components in row-major order."""
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    h, w = len(grid), len(grid[0])
    seen: set[Point] = set()
    result: list[frozenset[Point]] = []
    for r in range(h):
        for c in range(w):
            value = grid[r][c]
            if (r, c) in seen or (color is not None and value != color):
                continue
            if (value == background_color and not include_background and
                    color is None):
                continue
            seen.add((r, c))
            queue = deque([(r, c)])
            component: set[Point] = set()
            while queue:
                point = queue.popleft()
                component.add(point)
                for nxt in _neighbors(point, connectivity):
                    nr, nc = nxt
                    if not (0 <= nr < h and 0 <= nc < w) or nxt in seen:
                        continue
                    nxt_color = grid[nr][nc]
                    if nxt_color != value:
                        continue
                    if (nxt_color == background_color and
                            not include_background and color is None):
                        continue
                    seen.add(nxt)
                    queue.append(nxt)
            result.append(frozenset(component))
    return result


def _compute_relations_with_others(
    points: frozenset[Point], color: int, top: int, left: int, 
    bottom: int, right: int, width: int, height: int,
    centroid: tuple[float, float], symmetry: tuple[bool, bool, bool],
    orientation: str, perimeter: int, hole_count: int,
    touches_border: bool, touches_corner: bool,
    all_objects: list['ArcObject']) -> tuple[set[int], set[int], set[int], float, int | None, tuple]:
    """Compute relations with other objects without creating temporary ArcObjects."""
    enclosed_by_colors = set()
    contains_colors = set()
    adjacent_colors = set()
    nearest_dist = float('inf')
    nearest_color = None
    alignment_sig = []
    
    # Precompute this object's bbox and centroid for alignment checks
    this_bbox = (top, left, bottom, right)
    this_centroid = centroid
    
    for other in all_objects:
        if other.cells == points:
            continue
        
        # Check containment
        if points <= other.cells:
            enclosed_by_colors.add(other.color)
        if other.cells <= points:
            contains_colors.add(other.color)
        
        # Check adjacency
        is_adjacent = False
        for r, c in points:
            for or_, oc in other.cells:
                if abs(r - or_) + abs(c - oc) == 1:
                    is_adjacent = True
                    break
            if is_adjacent:
                break
        
        if is_adjacent:
            adjacent_colors.add(other.color)
        
        # Distance to nearest neighbor
        min_dist = min(
            abs(r - or_) + abs(c - oc)
            for r, c in points
            for or_, oc in other.cells
        )
        if min_dist < nearest_dist:
            nearest_dist = min_dist
            nearest_color = other.color
        
        # Alignment checks (center_row, center_column)
        # Center row alignment: horizontal overlap of bboxes
        if max(this_bbox[0], other.bbox[0]) < min(this_bbox[2], other.bbox[2]):
            alignment_sig.append(("h", other.color))
        # Center column alignment: vertical overlap of bboxes
        if max(this_bbox[1], other.bbox[1]) < min(this_bbox[3], other.bbox[3]):
            alignment_sig.append(("v", other.color))
    
    return (enclosed_by_colors, contains_colors, adjacent_colors, 
            nearest_dist, nearest_color, tuple(sorted(alignment_sig)))


def describe_object(color: int, cells: Iterable[Point], all_objects: list['ArcObject'] | None = None,
                    grid: Grid | None = None) -> ArcObject:
    points = frozenset(cells)
    if not points:
        raise ValueError("an object must contain at least one cell")
    top = min(r for r, _ in points)
    left = min(c for _, c in points)
    bottom = max(r for r, _ in points) + 1
    right = max(c for _, c in points) + 1
    height, width = bottom - top, right - left
    local = {(r - top, c - left) for r, c in points}
    horizontal = {(height - 1 - r, c) for r, c in local} == local
    vertical = {(r, width - 1 - c) for r, c in local} == local
    rotate180 = {(height - 1 - r, width - 1 - c) for r, c in local} == local
    if height == width == 1:
        orientation = "point"
    elif height == 1:
        orientation = "horizontal"
    elif width == 1:
        orientation = "vertical"
    elif height == width:
        orientation = "square"
    else:
        orientation = "wide" if width > height else "tall"
    
    # Compute enhanced features
    # Perimeter: count edges between object and background/other
    perimeter = 0
    for r, c in points:
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if (nr, nc) not in points:
                perimeter += 1
    
    # Hole detection: background cells fully enclosed by this object
    hole_count = 0
    if grid is not None:
        h, w = len(grid), len(grid[0])
        background = 0
        # Find background cells inside bbox
        for r in range(top + 1, bottom - 1):
            for c in range(left + 1, right - 1):
                if grid[r][c] == background and (r, c) not in points:
                    # Check if enclosed by this object's cells
                    if _is_enclosed_by_object(grid, points, (r, c), background):
                        hole_count += 1
    
    # Border and corner contact
    touches_border = top == 0 or left == 0 or bottom == (len(grid) if grid else 0) or right == (len(grid[0]) if grid else 0)
    touches_corner = (top == 0 and left == 0) or (top == 0 and right == (len(grid[0]) if grid else 0)) or \
                     (bottom == (len(grid) if grid else 0) and left == 0) or \
                     (bottom == (len(grid) if grid else 0) and right == (len(grid[0]) if grid else 0))
    
    # Relations with other objects
    this_bbox = (top, left, bottom, right)
    centroid = (sum(r for r, _ in points) / len(points),
                sum(c for _, c in points) / len(points))
    
    if all_objects:
        (enclosed_by_colors, contains_colors, adjacent_colors, 
         nearest_dist, nearest_color, alignment_sig) = _compute_relations_with_others(
            points, color, top, left, bottom, right, width, height,
            centroid, (horizontal, vertical, rotate180), orientation,
            perimeter, hole_count, touches_border, touches_corner,
            all_objects)
    else:
        enclosed_by_colors = contains_colors = adjacent_colors = set()
        nearest_dist = float('inf')
        nearest_color = None
        alignment_sig = ()
    
    # Density and compactness
    area = len(points)
    bbox_area = width * height
    density = area / bbox_area if bbox_area > 0 else 0.0
    compactness = (perimeter * perimeter) / area if area > 0 else 0.0
    
    # Create base object first (without relational signature)
    base_obj = ArcObject(
        color=color, cells=points, bbox=(top, left, bottom, right),
        width=width, height=height, centroid=centroid,
        symmetry=(horizontal, vertical, rotate180), orientation=orientation,
        perimeter=perimeter, hole_count=hole_count,
        touches_border=touches_border, touches_corner=touches_corner,
        enclosed_by=frozenset(enclosed_by_colors),
        contains_colors=frozenset(contains_colors),
        adjacent_colors=frozenset(adjacent_colors),
        nearest_neighbor_dist=nearest_dist,
        nearest_neighbor_color=nearest_color,
        alignment_signature=alignment_sig,
        density=density, compactness=compactness
    )
    
    # Compute relational signature if we have other objects
    if all_objects:
        rel_sig = compute_relational_signature(base_obj, all_objects, grid)
        # Create a new object with relational fields
        return ArcObject(
            color=base_obj.color, cells=base_obj.cells, bbox=base_obj.bbox,
            width=base_obj.width, height=base_obj.height, centroid=base_obj.centroid,
            symmetry=base_obj.symmetry, orientation=base_obj.orientation,
            perimeter=base_obj.perimeter, hole_count=base_obj.hole_count,
            touches_border=base_obj.touches_border, touches_corner=base_obj.touches_corner,
            enclosed_by=base_obj.enclosed_by, contains_colors=base_obj.contains_colors,
            adjacent_colors=base_obj.adjacent_colors,
            nearest_neighbor_dist=base_obj.nearest_neighbor_dist,
            nearest_neighbor_color=base_obj.nearest_neighbor_color,
            alignment_signature=base_obj.alignment_signature,
            density=base_obj.density, compactness=base_obj.compactness,
            left_of_colors=frozenset(rel_sig["left_of_colors"]),
            right_of_colors=frozenset(rel_sig["right_of_colors"]),
            above_colors=frozenset(rel_sig["above_colors"]),
            below_colors=frozenset(rel_sig["below_colors"]),
            same_row_colors=frozenset(rel_sig["same_row_colors"]),
            same_column_colors=frozenset(rel_sig["same_column_colors"]),
            between_pairs=frozenset(rel_sig["between_pairs"]),
            nearest_to_color=rel_sig["nearest_to_color"],
            farthest_from_color=rel_sig["farthest_from_color"],
            nth_from_left=rel_sig["nth_from_left"],
            nth_from_right=rel_sig["nth_from_right"],
            nth_from_top=rel_sig["nth_from_top"],
            nth_from_bottom=rel_sig["nth_from_bottom"],
            distance_to_colors=frozenset(rel_sig["distance_to_colors"]),
            closest_corner=rel_sig["closest_corner"],
            closest_edge=rel_sig["closest_edge"],
            relative_signature=tuple(sorted([
                ("left_of", tuple(sorted(rel_sig["left_of_colors"]))),
                ("right_of", tuple(sorted(rel_sig["right_of_colors"]))),
                ("above", tuple(sorted(rel_sig["above_colors"]))),
                ("below", tuple(sorted(rel_sig["below_colors"]))),
                ("same_row", tuple(sorted(rel_sig["same_row_colors"]))),
                ("same_column", tuple(sorted(rel_sig["same_column_colors"]))),
                ("between", tuple(sorted(rel_sig["between_pairs"]))),
                ("nearest_to", rel_sig["nearest_to_color"]),
                ("farthest_from", rel_sig["farthest_from_color"]),
                ("nth_left", rel_sig["nth_from_left"]),
                ("nth_right", rel_sig["nth_from_right"]),
                ("nth_top", rel_sig["nth_from_top"]),
                ("nth_bottom", rel_sig["nth_from_bottom"]),
            ]))
        )
    return base_obj


def _is_enclosed_by_object(grid: Grid, obj_cells: frozenset[Point], 
                           start: Point, background: int) -> bool:
    """Check if a background cell is enclosed by the object."""
    h, w = len(grid), len(grid[0])
    queue = deque([start])
    seen = {start}
    while queue:
        r, c = queue.popleft()
        # If we reach border, not enclosed
        if r == 0 or r == h - 1 or c == 0 or c == w - 1:
            return False
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in seen:
                if grid[nr][nc] == background and (nr, nc) not in obj_cells:
                    seen.add((nr, nc))
                    queue.append((nr, nc))
    return True


# ============================================================
# NEW RELATIONAL PREDICATES
# ============================================================

def left_of(a: ArcObject, b: ArcObject) -> bool:
    """Object a is to the left of object b (a's right edge <= b's left edge)."""
    return a.bbox[3] <= b.bbox[1]


def right_of(a: ArcObject, b: ArcObject) -> bool:
    """Object a is to the right of object b (a's left edge >= b's right edge)."""
    return a.bbox[1] >= b.bbox[3]


def above(a: ArcObject, b: ArcObject) -> bool:
    """Object a is above object b (a's bottom edge <= b's top edge)."""
    return a.bbox[2] <= b.bbox[0]


def below(a: ArcObject, b: ArcObject) -> bool:
    """Object a is below object b (a's top edge >= b's bottom edge)."""
    return a.bbox[0] >= b.bbox[2]


def same_row(a: ArcObject, b: ArcObject) -> bool:
    """Objects share horizontal space (their vertical spans overlap)."""
    return max(a.bbox[0], b.bbox[0]) < min(a.bbox[2], b.bbox[2])


def same_column(a: ArcObject, b: ArcObject) -> bool:
    """Objects share vertical space (their horizontal spans overlap)."""
    return max(a.bbox[1], b.bbox[1]) < min(a.bbox[3], b.bbox[3])


def between(obj: ArcObject, a: ArcObject, b: ArcObject) -> bool:
    """Object is horizontally between a and b (a left of obj left of b, or b left of obj left of a)."""
    return (left_of(a, obj) and left_of(obj, b)) or (left_of(b, obj) and left_of(obj, a))


def vertically_between(obj: ArcObject, a: ArcObject, b: ArcObject) -> bool:
    """Object is vertically between a and b."""
    return (above(a, obj) and above(obj, b)) or (above(b, obj) and above(obj, a))


def nth_from_left(obj: ArcObject, objects: list[ArcObject], n: int) -> bool:
    """Object is the n-th from the left among objects (1-indexed)."""
    sorted_objs = sorted(objects, key=lambda o: o.centroid[1])
    if 1 <= n <= len(sorted_objs):
        return sorted_objs[n - 1].cells == obj.cells
    return False


def nth_from_right(obj: ArcObject, objects: list[ArcObject], n: int) -> bool:
    """Object is the n-th from the right among objects (1-indexed)."""
    sorted_objs = sorted(objects, key=lambda o: o.centroid[1], reverse=True)
    if 1 <= n <= len(sorted_objs):
        return sorted_objs[n - 1].cells == obj.cells
    return False


def nth_from_top(obj: ArcObject, objects: list[ArcObject], n: int) -> bool:
    """Object is the n-th from the top among objects (1-indexed)."""
    sorted_objs = sorted(objects, key=lambda o: o.centroid[0])
    if 1 <= n <= len(sorted_objs):
        return sorted_objs[n - 1].cells == obj.cells
    return False


def nth_from_bottom(obj: ArcObject, objects: list[ArcObject], n: int) -> bool:
    """Object is the n-th from the bottom among objects (1-indexed)."""
    sorted_objs = sorted(objects, key=lambda o: o.centroid[0], reverse=True)
    if 1 <= n <= len(sorted_objs):
        return sorted_objs[n - 1].cells == obj.cells
    return False


def manhattan_distance(a: ArcObject, b: ArcObject) -> float:
    """Manhattan distance between object centroids."""
    return abs(a.centroid[0] - b.centroid[0]) + abs(a.centroid[1] - b.centroid[1])


def chebyshev_distance(a: ArcObject, b: ArcObject) -> float:
    """Chebyshev distance between object centroids."""
    return max(abs(a.centroid[0] - b.centroid[0]), abs(a.centroid[1] - b.centroid[1]))


def euclidean_distance(a: ArcObject, b: ArcObject) -> float:
    """Euclidean distance between object centroids."""
    dy = a.centroid[0] - b.centroid[0]
    dx = a.centroid[1] - b.centroid[1]
    return (dy * dy + dx * dx) ** 0.5


def nearest_to(obj: ArcObject, objects: list[ArcObject]) -> ArcObject | None:
    """Find the nearest object to obj (excluding self) using Manhattan distance."""
    candidates = [o for o in objects if o.cells != obj.cells]
    if not candidates:
        return None
    return min(candidates, key=lambda o: manhattan_distance(obj, o))


def farthest_from(obj: ArcObject, objects: list[ArcObject]) -> ArcObject | None:
    """Find the farthest object from obj (excluding self) using Manhattan distance."""
    candidates = [o for o in objects if o.cells != obj.cells]
    if not candidates:
        return None
    return max(candidates, key=lambda o: manhattan_distance(obj, o))


def same_distance(a: ArcObject, b: ArcObject, c: ArcObject) -> bool:
    """Objects a and b are at the same distance from c."""
    return abs(manhattan_distance(a, c) - manhattan_distance(b, c)) < 1e-9


def closest_to_corner(obj: ArcObject, grid: Grid) -> str:
    """Determine which corner the object is closest to."""
    h, w = len(grid), len(grid[0])
    corners = {
        "top_left": (0, 0),
        "top_right": (0, w - 1),
        "bottom_left": (h - 1, 0),
        "bottom_right": (h - 1, w - 1),
    }
    obj_center = obj.centroid
    return min(corners.keys(), key=lambda k: abs(obj_center[0] - corners[k][0]) + abs(obj_center[1] - corners[k][1]))


def closest_to_edge(obj: ArcObject, grid: Grid) -> str:
    """Determine which edge the object is closest to."""
    h, w = len(grid), len(grid[0])
    r, c = obj.centroid
    distances = {
        "top": r,
        "bottom": h - 1 - r,
        "left": c,
        "right": w - 1 - c,
    }
    return min(distances, key=distances.get)


def same_relative_position(a: ArcObject, b: ArcObject, c: ArcObject, d: ArcObject) -> bool:
    """Check if relative position from a to b equals relative position from c to d."""
    dy1 = b.centroid[0] - a.centroid[0]
    dx1 = b.centroid[1] - a.centroid[1]
    dy2 = d.centroid[0] - c.centroid[0]
    dx2 = d.centroid[1] - c.centroid[1]
    return abs(dy1 - dy2) < 1e-9 and abs(dx1 - dx2) < 1e-9


def relative_offset(a: ArcObject, b: ArcObject) -> tuple[int, int]:
    """Return (dy, dx) from object a to object b."""
    return (int(round(b.centroid[0] - a.centroid[0])), int(round(b.centroid[1] - a.centroid[1])))


def aligned_with(a: ArcObject, b: ArcObject, c: ArcObject) -> bool:
    """Check if a, b, c are collinear (approximately)."""
    # Check if b is on the line between a and c
    dy1 = b.centroid[0] - a.centroid[0]
    dx1 = b.centroid[1] - a.centroid[1]
    dy2 = c.centroid[0] - a.centroid[0]
    dx2 = c.centroid[1] - a.centroid[1]
    # Cross product should be near zero for collinearity
    return abs(dy1 * dx2 - dx1 * dy2) < 1e-9


def compute_relational_signature(obj: ArcObject, all_objects: list[ArcObject], grid: Grid | None = None) -> dict:
    """Compute comprehensive relational signature for an object."""
    signature = {
        "left_of_colors": set(),
        "right_of_colors": set(),
        "above_colors": set(),
        "below_colors": set(),
        "same_row_colors": set(),
        "same_column_colors": set(),
        "between_pairs": set(),
        "nearest_to_color": None,
        "farthest_from_color": None,
        "nth_from_left": None,
        "nth_from_right": None,
        "nth_from_top": None,
        "nth_from_bottom": None,
        "distance_to_colors": [],
        "closest_corner": None,
        "closest_edge": None,
    }
    
    if not all_objects or len(all_objects) < 2:
        return signature
    
    others = [o for o in all_objects if o.cells != obj.cells]
    if not others:
        return signature
    
    # Horizontal relations
    for other in others:
        if left_of(obj, other):
            signature["left_of_colors"].add(other.color)
        if right_of(obj, other):
            signature["right_of_colors"].add(other.color)
        if above(obj, other):
            signature["above_colors"].add(other.color)
        if below(obj, other):
            signature["below_colors"].add(other.color)
        if same_row(obj, other):
            signature["same_row_colors"].add(other.color)
        if same_column(obj, other):
            signature["same_column_colors"].add(other.color)
    
    # Between relations (check all pairs)
    for i, a in enumerate(others):
        for b in others[i+1:]:
            if between(obj, a, b):
                signature["between_pairs"].add((a.color, b.color))
            if vertically_between(obj, a, b):
                signature["between_pairs"].add((a.color, b.color))
    
    # Nth from edges
    all_objs = [obj] + others
    # Left/right
    left_sorted = sorted(all_objs, key=lambda o: o.centroid[1])
    for idx, o in enumerate(left_sorted):
        if o.cells == obj.cells:
            signature["nth_from_left"] = idx + 1
            signature["nth_from_right"] = len(left_sorted) - idx
            break
    
    # Top/bottom
    top_sorted = sorted(all_objs, key=lambda o: o.centroid[0])
    for idx, o in enumerate(top_sorted):
        if o.cells == obj.cells:
            signature["nth_from_top"] = idx + 1
            signature["nth_from_bottom"] = len(top_sorted) - idx
            break
    
    # Nearest/farthest
    nearest = nearest_to(obj, others)
    if nearest:
        signature["nearest_to_color"] = nearest.color
    farthest = farthest_from(obj, others)
    if farthest:
        signature["farthest_from_color"] = farthest.color
    
    # Distances to all other colors
    signature["distance_to_colors"] = [
        (o.color, manhattan_distance(obj, o)) for o in others
    ]
    
    # Closest corner/edge (if grid provided)
    if grid is not None:
        signature["closest_corner"] = closest_to_corner(obj, grid)
        signature["closest_edge"] = closest_to_edge(obj, grid)
    
    return signature


def extract_objects(grid: Grid, connectivity: Connectivity = 4,
                    include_background: bool = False,
                    background_color: int = 0) -> list[ArcObject]:
    """Extract objects with full feature computation."""
    # First pass: get basic components
    components = connected_components(grid, connectivity=connectivity,
                                      include_background=include_background,
                                      background_color=background_color)
    basic_objects = []
    for component in components:
        r, c = min(component)
        # Create minimal object for relation computation
        points = frozenset(component)
        top = min(r for r, _ in points)
        left = min(c for _, c in points)
        bottom = max(r for r, _ in points) + 1
        right = max(c for _, c in points) + 1
        width, height = right - left, bottom - top
        local = {(r - top, c - left) for r, c in points}
        horizontal = {(height - 1 - r, c) for r, c in local} == local
        vertical = {(r, width - 1 - c) for r, c in local} == local
        rotate180 = {(height - 1 - r, width - 1 - c) for r, c in local} == local
        if height == width == 1:
            orientation = "point"
        elif height == 1:
            orientation = "horizontal"
        elif width == 1:
            orientation = "vertical"
        elif height == width:
            orientation = "square"
        else:
            orientation = "wide" if width > height else "tall"
        centroid = (sum(r for r, _ in points) / len(points),
                    sum(c for _, c in points) / len(points))
        basic_objects.append(ArcObject(
            color=grid[r][c], cells=points, bbox=(top, left, bottom, right),
            width=width, height=height, centroid=centroid,
            symmetry=(horizontal, vertical, rotate180), orientation=orientation,
            perimeter=0, hole_count=0, touches_border=False, touches_corner=False,
            enclosed_by=frozenset(), contains_colors=frozenset(),
            adjacent_colors=frozenset(), nearest_neighbor_dist=float('inf'),
            nearest_neighbor_color=None, alignment_signature=(),
            density=0.0, compactness=0.0
        ))
    
    # Second pass: compute full features for each object
    full_objects = []
    for component in components:
        r, c = min(component)
        obj = describe_object(grid[r][c], component, basic_objects, grid)
        full_objects.append(obj)
    
    return full_objects


def relative_position(a: ArcObject, b: ArcObject) -> str:
    """Return the dominant compass direction from object a to object b."""
    dy = b.centroid[0] - a.centroid[0]
    dx = b.centroid[1] - a.centroid[1]
    if dy == 0 and dx == 0:
        return "overlap"
    if abs(dy) > 2 * abs(dx):
        return "below" if dy > 0 else "above"
    if abs(dx) > 2 * abs(dy):
        return "right" if dx > 0 else "left"
    return ("below-" if dy > 0 else "above-") + ("right" if dx > 0 else "left")


def color_relationships(grid: Grid) -> dict:
    counts: dict[int, int] = {}
    for row in grid:
        for value in row:
            if value:
                counts[value] = counts.get(value, 0) + 1
    objects = extract_objects(grid)
    by_color: dict[int, list[ArcObject]] = {}
    for obj in objects:
        by_color.setdefault(obj.color, []).append(obj)
    return {
        "cell_counts": dict(sorted(counts.items())),
        "object_counts": {color: len(items) for color, items in sorted(by_color.items())},
        "object_colors": tuple(sorted(by_color)),
    }


def contained(inner: ArcObject, outer: ArcObject) -> bool:
    return inner.cells <= outer.cells


def aligned(a: ArcObject, b: ArcObject, axis: str = "row") -> bool:
    if axis == "row":
        return max(a.bbox[0], b.bbox[0]) < min(a.bbox[2], b.bbox[2])
    if axis == "column":
        return max(a.bbox[1], b.bbox[1]) < min(a.bbox[3], b.bbox[3])
    if axis == "center_row":
        return a.centroid[0] == b.centroid[0]
    if axis == "center_column":
        return a.centroid[1] == b.centroid[1]
    if axis == "top":
        return a.bbox[0] == b.bbox[0]
    if axis == "bottom":
        return a.bbox[2] == b.bbox[2]
    if axis == "left":
        return a.bbox[1] == b.bbox[1]
    if axis == "right":
        return a.bbox[3] == b.bbox[3]
    raise ValueError(f"unknown alignment axis: {axis}")


def adjacent(a: ArcObject, b: ArcObject, diagonal: bool = False) -> bool:
    for r, c in a.cells:
        for rr, cc in b.cells:
            distance = max(abs(r - rr), abs(c - cc)) if diagonal else abs(r - rr) + abs(c - cc)
            if distance == 1:
                return True
    return False


def object_relations(a: ArcObject, b: ArcObject) -> frozenset[str]:
    """Describe structural relations between two symbolic objects."""
    relations: set[str] = set()
    if a.color == b.color:
        relations.add("same_color")
    a_shape = normalized_shape(a)
    b_shape = normalized_shape(b)
    if a_shape == b_shape:
        relations.add("same_shape")
    if len(a.cells) == len(b.cells):
        relations.add("same_size")
    if a.cells & b.cells:
        relations.add("overlapping")
    if contained(a, b):
        relations.add("inside")
    if contained(b, a):
        relations.add("contains")
    if adjacent(a, b):
        relations.update(("adjacent", "touching"))
    if aligned(a, b, "center_row"):
        relations.update(("aligned_x", "same_row"))
    if aligned(a, b, "center_column"):
        relations.update(("aligned_y", "same_column"))
    ar0, ac0, ar1, ac1 = a.bbox
    br0, bc0, br1, bc1 = b.bbox
    if ar1 == br0:
        relations.add("immediately_above")
    if br1 == ar0:
        relations.add("immediately_below")
    if ac1 == bc0:
        relations.add("immediately_left")
    if bc1 == ac0:
        relations.add("immediately_right")
    return frozenset(relations)


def normalized_shape(obj: ArcObject) -> tuple:
    """Color- and position-independent object geometry signature."""
    top, left, _, _ = obj.bbox
    return (obj.height, obj.width,
            tuple(sorted((r - top, c - left) for r, c in obj.cells)))


def enclosed_background_cells(grid: Grid, background: int = 0) -> frozenset[Point]:
    """Find all background cells that cannot reach any canvas edge."""
    h, w = len(grid), len(grid[0])
    starts = {(r, c) for r in range(h) for c in range(w)
              if (r in (0, h - 1) or c in (0, w - 1))
              and grid[r][c] == background}
    queue = deque(starts)
    seen = set(starts)
    while queue:
        rr, cc = queue.popleft()
        for nxt in _neighbors((rr, cc), 4):
            nr, nc = nxt
            if (0 <= nr < h and 0 <= nc < w and nxt not in seen
                    and grid[nr][nc] == background):
                seen.add(nxt)
                queue.append(nxt)
    return frozenset((r, c) for r in range(h) for c in range(w)
                     if grid[r][c] == background and (r, c) not in seen)


def encloses(grid: Grid, point: Point, background: int = 0) -> bool:
    """Whether a background cell cannot reach the canvas boundary."""
    r, c = point
    if not (0 <= r < len(grid) and 0 <= c < len(grid[0])):
        return False
    return point in enclosed_background_cells(grid, background)
