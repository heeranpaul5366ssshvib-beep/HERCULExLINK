"""Small, replayable hypotheses inferred from ARC demonstrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .deltas import compare_grids
from .grid import Grid, dimensions
from .objects import extract_objects
from .primitives import (complete_symmetry, crop_color, crop_non_background,
                          combine_regions, fill_enclosed_background, gravity,
                          object_bounding_boxes, object_feature, object_outlines,
                          recolor_by_palette_rank, recolor_objects_by_feature,
                          connect_aligned_objects, reflect_horizontal,
                          connect_nearest_objects,
                          reflect_vertical, rotate, scale, select_objects,
                          split_on_separator, tile, transform_each_object)

Transform = Callable[[Grid], Grid]


@dataclass(frozen=True)
class Rule:
    name: str
    apply: Transform
    complexity: int
    assumptions: int = 0
    family: str = "grid-transform"
    matched_examples: int = 0
    structural_coverage: int = 0
    known_colors: tuple[int, ...] = ()
    relation_predicates: tuple[str, ...] = ()
    local_writes: int = 0
    invariance_passes: tuple[str, ...] = ()
    invariance_failures: tuple[str, ...] = ()
    relation_perturbation: Callable[[Grid], bool | None] | None = None


def _fits(transform: Transform, pairs: tuple[tuple[Grid, Grid], ...]) -> bool:
    try:
        return all(transform(source) == target for source, target in pairs)
    except (ArithmeticError, IndexError, TypeError, ValueError):
        return False


def _mapping_rule(pairs: tuple[tuple[Grid, Grid], ...], preprocess: Transform,
                  name: str, complexity: int = 2) -> Rule | None:
    mapping: dict[int, int] = {}
    for source, target in pairs:
        source = preprocess(source)
        if dimensions(source) != dimensions(target):
            return None
        for row_a, row_b in zip(source, target):
            for a, b in zip(row_a, row_b):
                if a in mapping and mapping[a] != b:
                    return None
                mapping[a] = b
    if not any(a != b for a, b in mapping.items()):
        return None
    known_colors = tuple(sorted({value for source, _ in pairs
                                 for row in preprocess(source) for value in row}))
    return Rule(name, lambda grid, preprocess=preprocess, mapping=mapping: tuple(
        tuple(mapping.get(v, v) for v in row)
        for row in preprocess(grid)),
        complexity=complexity, assumptions=1, family="color",
        known_colors=known_colors)


def _count_rules(pairs: tuple[tuple[Grid, Grid], ...]) -> Iterable[Rule]:
    if not pairs or any(dimensions(target) != (1, 1) for _, target in pairs):
        return
    colors = sorted({value for grid, _ in pairs for row in grid for value in row if value})
    metrics = [
        ("nonbackground-cell-count", lambda g: sum(v != 0 for row in g for v in row)),
        ("connected-object-count", lambda g: sum(v != 0 for row in g for v in row)),
        ("distinct-color-count", lambda g: len({v for row in g for v in row if v})),
    ]
    from .objects import connected_components
    metrics[1] = (metrics[1][0], lambda g: len(connected_components(g)))
    metrics.extend((f"color-{color}-cell-count",
                    lambda g, color=color: sum(v == color for row in g for v in row))
                   for color in colors)
    metrics.extend((f"color-{color}-object-count",
                    lambda g, color=color: len(connected_components(g, color=color)))
                   for color in colors)
    for name, measure in metrics:
        if all(target[0][0] == measure(source) for source, target in pairs):
            yield Rule(name, lambda grid, measure=measure: ((measure(grid),),),
                       complexity=2, assumptions=1, family="counting")


def _local_rewrite_rule(pairs: tuple[tuple[Grid, Grid], ...], radius: int) -> Rule | None:
    if any(dimensions(source) != dimensions(target) for source, target in pairs):
        return None
    contexts: dict[tuple[int, ...], int] = {}
    counts: dict[tuple[int, ...], int] = {}
    example_support: dict[tuple[int, ...], set[int]] = {}
    changed_support: dict[tuple[int, ...], set[int]] = {}
    for example_index, (source, target) in enumerate(pairs):
        h, w = dimensions(source)
        for r in range(h):
            for c in range(w):
                context = tuple(
                    source[rr][cc] if 0 <= rr < h and 0 <= cc < w else -1
                    for rr in range(r - radius, r + radius + 1)
                    for cc in range(c - radius, c + radius + 1))
                output = target[r][c]
                if context in contexts and contexts[context] != output:
                    return None
                contexts[context] = output
                counts[context] = counts.get(context, 0) + 1
                example_support.setdefault(context, set()).add(example_index)
                center = context[len(context) // 2]
                if output != center:
                    changed_support.setdefault(context, set()).add(example_index)
    reused = sum(len(indices) >= 2 for indices in example_support.values())
    # A local program must show a changed context recurring across separate
    # demonstrations. Repetition among neighboring cells in one grid is not
    # evidence that the rule generalizes beyond that one configuration.
    supported_changes = sum(len(indices) >= 2
                            for indices in changed_support.values())
    if reused < 2 or supported_changes < 1:
        return None

    def apply(grid: Grid) -> Grid:
        h, w = dimensions(grid)
        rows = []
        for r in range(h):
            row = []
            for c in range(w):
                context = tuple(
                    grid[rr][cc] if 0 <= rr < h and 0 <= cc < w else -1
                    for rr in range(r - radius, r + radius + 1)
                    for cc in range(c - radius, c + radius + 1))
                row.append(contexts.get(context, grid[r][c]))
            rows.append(tuple(row))
        return tuple(rows)

    return Rule(f"local-neighborhood-r{radius}", apply,
                complexity=12 + radius * 4, assumptions=3,
                family="local-rewrite", structural_coverage=reused,
                local_writes=supported_changes)


def _palette_rank_rule(pairs: tuple[tuple[Grid, Grid], ...],
                       measure: str, preprocess: Transform,
                       name: str) -> Rule | None:
    rank_mapping: dict[int, int] = {}
    for source, target in pairs:
        source = preprocess(source)
        if dimensions(source) != dimensions(target):
            return None
        palette = {value for row in source for value in row}
        target_palette = {value for row in target for value in row}
        if not target_palette <= palette:
            return None
        if measure == "cells":
            counts = {color: sum(value == color for row in source for value in row)
                      for color in palette}
        else:
            from .objects import connected_components
            counts = {color: (0 if color == 0 else
                              len(connected_components(source, color=color)))
                      for color in palette}
        ordered = sorted(palette, key=lambda color: (-counts[color], color))
        color_to_rank = {color: rank for rank, color in enumerate(ordered)}
        for row_a, row_b in zip(source, target):
            for a, b in zip(row_a, row_b):
                source_rank, target_rank = color_to_rank[a], color_to_rank[b]
                if (source_rank in rank_mapping and
                        rank_mapping[source_rank] != target_rank):
                    return None
                rank_mapping[source_rank] = target_rank
    if not rank_mapping or all(rank == target for rank, target in rank_mapping.items()):
        return None
    return Rule(name, lambda grid, preprocess=preprocess,
                rank_mapping=rank_mapping, measure=measure: recolor_by_palette_rank(
                    preprocess(grid), rank_mapping, measure),
                complexity=5, assumptions=2, family="palette-role")


def _object_correspondence_rule(
        pairs: tuple[tuple[Grid, Grid], ...]) -> Rule | None:
    """Infer a shared per-shape/color translation and recoloring from demos."""
    from .primitives import object_shape_signature, transform_objects_by_signature

    transforms: dict[tuple, tuple[int, int, int]] = {}
    observed = 0
    for source, target in pairs:
        if dimensions(source) != dimensions(target):
            return None
        source_objects = extract_objects(source)
        target_objects = extract_objects(target)
        if len(source_objects) != len(target_objects):
            return None
        unused = set(range(len(target_objects)))
        for obj in source_objects:
            shape = object_shape_signature(obj)
            candidates = [index for index in unused
                          if object_shape_signature(target_objects[index]) == shape]
            if not candidates:
                return None
            same_color = [index for index in candidates
                          if target_objects[index].color == obj.color]
            if len(same_color) == 1:
                selected = same_color[0]
            elif len(candidates) == 1:
                selected = candidates[0]
            else:
                # Correspondence among indistinguishable recolored shapes is
                # ambiguous; do not invent a coordinate-based tie breaker.
                return None
            output_object = target_objects[selected]
            key = (obj.color, shape)
            transform = (output_object.bbox[0] - obj.bbox[0],
                         output_object.bbox[1] - obj.bbox[1],
                         output_object.color)
            if key in transforms and transforms[key] != transform:
                return None
            transforms[key] = transform
            unused.remove(selected)
            observed += 1
        if unused:
            return None
    if not transforms or all(value == (0, 0, key[0])
                             for key, value in transforms.items()):
        return None

    def apply(grid: Grid, transforms=transforms) -> Grid:
        return transform_objects_by_signature(grid, transforms)

    if not _fits(apply, pairs):
        return None
    return Rule("object-correspondence(shape,color)", apply,
                complexity=4 + len(transforms), assumptions=2,
                family="object-correspondence",
                structural_coverage=observed,
                known_colors=tuple(sorted({key[0] for key in transforms})))


def generate_hypotheses(train_pairs: Iterable[tuple[Grid, Grid]], *,
                        return_search_stats: bool = False):
    """Generate direct and composed candidates; replay remains authoritative.

    If direct rules cannot replay every demonstration, use a bounded program
    search over grid/object/relation operators. Search output is only a source
    of hypotheses: the caller still verifies every returned rule exactly.
    """
    pairs = tuple(train_pairs)
    if not pairs:
        return ([], {"triggered": False, "reason": "no_training_pairs"}) \
            if return_search_stats else []
    geometries: list[tuple[str, Transform, int]] = [
        ("identity", lambda g: g, 1),
        ("reflect-horizontal", reflect_horizontal, 2),
        ("reflect-vertical", reflect_vertical, 2),
        ("reflect-both-axes", lambda g: reflect_vertical(reflect_horizontal(g)), 3),
        ("rotate-90", lambda g: rotate(g, 1), 2),
        ("rotate-180", lambda g: rotate(g, 2), 2),
        ("rotate-270", lambda g: rotate(g, 3), 2),
        ("crop-non-background", crop_non_background, 2),
    ]
    rules: list[Rule] = [
        Rule("identity", lambda g: g, 1, family="identity"),
        Rule("reflect-horizontal", reflect_horizontal, 2),
        Rule("reflect-vertical", reflect_vertical, 2),
        Rule("reflect-both-axes", lambda g: reflect_vertical(reflect_horizontal(g)), 3),
        Rule("rotate-90", lambda g: rotate(g, 1), 2),
        Rule("rotate-180", lambda g: rotate(g, 2), 2),
        Rule("rotate-270", lambda g: rotate(g, 3), 2),
        Rule("crop-non-background", crop_non_background, 2, assumptions=1),
    ]
    for axis in ("vertical", "horizontal", "diagonal", "antidiagonal"):
        transform = lambda g, axis=axis: complete_symmetry(g, axis)
        if _fits(transform, pairs):
            rules.append(Rule(f"complete-symmetry({axis})", transform, 3,
                              assumptions=1, family="symmetry"))
    for name, transform, complexity in (
            ("fill-enclosed", fill_enclosed_background, 3),
            ("fill-object-bboxes", object_bounding_boxes, 3),
            ("object-outlines", object_outlines, 3)):
        if _fits(transform, pairs):
            rules.append(Rule(name, transform, complexity, assumptions=1,
                              family="object-transform"))
    selectors = ("largest", "smallest", "unique-size", "unique-shape",
                 "most-frequent-color", "least-frequent-color", "symmetric",
                 "asymmetric", "horizontal", "vertical", "square", "point",
                 "wide", "tall")
    for selector in selectors:
        transform = lambda g, selector=selector: select_objects(g, selector)
        if _fits(transform, pairs):
            rules.append(Rule(f"select-objects({selector})", transform, 3,
                              assumptions=1, family="object-selection"))
        cropped = lambda g, transform=transform: crop_non_background(transform(g))
        if _fits(cropped, pairs):
            rules.append(Rule(f"crop-selected-objects({selector})", cropped, 4,
                              assumptions=2, family="object-selection"))
    for operation in ("reflect-horizontal", "reflect-vertical", "rotate-90",
                      "rotate-180", "rotate-270"):
        transform = lambda g, operation=operation: transform_each_object(g, operation)
        if _fits(transform, pairs):
            rules.append(Rule(f"transform-each-object({operation})", transform, 4,
                              assumptions=1, family="object-transform"))
    # Learn a global object-property -> output-color map from demonstrations.
    for feature in ("size", "shape", "orientation", "symmetry", "dimensions"):
        mapping = {}
        consistent = True
        for source, target in pairs:
            if dimensions(source) != dimensions(target):
                consistent = False
                break
            for obj in extract_objects(source):
                colors_at_object = {target[r][c] for r, c in obj.cells}
                if len(colors_at_object) != 1:
                    consistent = False
                    break
                key = object_feature(obj, feature)
                color = next(iter(colors_at_object))
                if key in mapping and mapping[key] != color:
                    consistent = False
                    break
                mapping[key] = color
            if not consistent:
                break
        if consistent and mapping:
            transform = lambda g, mapping=mapping, feature=feature: \
                recolor_objects_by_feature(g, mapping, feature)
            if _fits(transform, pairs):
                rules.append(Rule(f"recolor-objects-by-{feature}", transform, 4,
                                  assumptions=1, family="object-recolor"))
    for direction in ("up", "down", "left", "right"):
        transform = lambda g, direction=direction: gravity(g, direction)
        if _fits(transform, pairs):
            rules.append(Rule(f"gravity-{direction}", transform, 4,
                              assumptions=1, family="object-movement"))
    correspondence = _object_correspondence_rule(pairs)
    if correspondence:
        rules.append(correspondence)
    from .relations import generate_relation_copy_hypotheses
    rules.extend(generate_relation_copy_hypotheses(pairs))
    for color_policy in ("same", "first", "second"):
        transform = lambda g, color_policy=color_policy: \
            connect_aligned_objects(g, color_policy)
        if _fits(transform, pairs):
            rules.append(Rule(f"connect-aligned({color_policy})", transform, 5,
                              assumptions=2, family="object-relations"))
    if any(source != target for source, target in pairs):
        for route in ("horizontal-first", "vertical-first"):
            for color_policy in ("same", "first", "second"):
                transform = lambda g, route=route, color_policy=color_policy: \
                    connect_nearest_objects(g, route, color_policy)
                if _fits(transform, pairs):
                    rules.append(Rule(
                        f"connect-nearest({route},{color_policy})", transform, 7,
                        assumptions=3, family="object-relations"))
    for axis in ("horizontal", "vertical"):
        for operation in ("union", "intersection", "xor",
                          "subtract-left", "subtract-right"):
            def combine_halves(grid: Grid, axis=axis, operation=operation) -> Grid:
                regions = split_on_separator(grid, axis)
                if len(regions) != 2:
                    raise ValueError("expected exactly two regions around a separator")
                return combine_regions(regions[0], regions[1], operation)
            if _fits(combine_halves, pairs):
                rules.append(Rule(f"split-{axis}-{operation}", combine_halves, 4,
                                  assumptions=2, family="region-combination"))
    for name, transform, complexity in geometries[1:]:
        mapped = _mapping_rule(pairs, transform,
                               f"{name}+color-map", complexity + 2)
        if mapped:
            rules.append(mapped)
    for name, transform, complexity in geometries:
        for measure in ("cells", "objects"):
            role_rule = _palette_rank_rule(
                pairs, measure, transform,
                f"{name}+palette-role-{measure}")
            if role_rule:
                rules.append(role_rule)
    for direction in ("up", "down", "left", "right"):
        transform = lambda g, direction=direction: gravity(g, direction)
        mapped = _mapping_rule(pairs, transform,
                               f"gravity-{direction}+color-map", 6)
        if mapped:
            rules.append(mapped)

    # Retain one color at a time; crop its symbolic object region as a second
    # hypothesis. These parameters come from visible training colors only.
    input_colors = sorted({value for source, _ in pairs
                           for row in source for value in row if value != 0})
    for color in input_colors:
        keep = lambda grid, color=color: tuple(
            tuple(value if value == color else 0 for value in row) for row in grid)
        for suffix, transform, complexity in (
                ("keep-color", keep, 2),
                ("crop-color", lambda g, keep=keep: crop_non_background(keep(g)), 3)):
            if _fits(transform, pairs):
                rules.append(Rule(f"{suffix}({color})", transform, complexity,
                                  assumptions=1, family="object-selection"))
            mapped = _mapping_rule(pairs, transform,
                                   f"{suffix}({color})+color-map", complexity + 2)
            if mapped:
                rules.append(mapped)

    # Shallow compositions cover common "select/crop, then transform" rules.
    # Only two operations are composed; all parameters are fixed by the DSL.
    simple_ops: list[tuple[str, Transform, int]] = [
        item for item in geometries if item[0] != "identity"
    ]
    for color in input_colors:
        simple_ops.append((f"keep-color({color})",
                           lambda g, color=color: tuple(
                               tuple(v if v == color else 0 for v in row) for row in g), 2))
        simple_ops.append((f"crop-color({color})",
                           lambda g, color=color: crop_color(g, color), 3))
        simple_ops.append((f"fill-holes({color})",
                           lambda g, color=color: fill_enclosed_background(g, color), 3))
    for selector in selectors:
        simple_ops.append((f"select-objects({selector})",
                           lambda g, selector=selector: select_objects(g, selector), 3))
    for operation in ("reflect-horizontal", "reflect-vertical", "rotate-90",
                      "rotate-180", "rotate-270"):
        simple_ops.append((f"transform-each-object({operation})",
                           lambda g, operation=operation:
                           transform_each_object(g, operation), 4))
    simple_ops.append(("fill-holes-majority", fill_enclosed_background, 3))
    # Avoid the Cartesian product of unrelated selectors; geometric stages
    # may be composed with one selection/cropping/filling stage in either order.
    geometric = [item for item in geometries
                 if item[0].startswith(("reflect", "rotate", "crop-non-background"))]
    structural = [item for item in simple_ops
                  if item[0].startswith(("keep-color", "crop-color", "fill-holes",
                                         "select-objects", "transform-each-object"))]
    for geom_name, geom, geom_cost in geometric:
        for struct_name, struct, struct_cost in structural:
            for order, first, second in (("then", geom, struct),
                                         ("then", struct, geom)):
                transform = lambda grid, first=first, second=second: second(first(grid))
                name = f"{geom_name}+{struct_name}" if first is geom else f"{struct_name}+{geom_name}"
                if _fits(transform, pairs):
                    rules.append(Rule(name, transform, geom_cost + struct_cost,
                                      assumptions=2, family="composition"))

    # Fixed-offset translation rules are removed. Relation-conditioned
    # copy/place (generated via generate_relation_copy_hypotheses) is the
    # only object-copy mechanism. Constant (dy, dx) hypotheses do not
    # generalize when landmarks move.

    first_in, first_out = pairs[0]
    h0, w0 = dimensions(first_in)
    h1, w1 = dimensions(first_out)
    if h1 % h0 == 0 and w1 % w0 == 0:
        sy, sx = h1 // h0, w1 // w0
        if (sy > 1 or sx > 1) and all(
                scale(source, sy, sx) == target for source, target in pairs
                if dimensions(target) == (dimensions(source)[0] * sy,
                                          dimensions(source)[1] * sx)) and all(
                dimensions(target) == (dimensions(source)[0] * sy,
                                       dimensions(source)[1] * sx)
                for source, target in pairs):
            rules.append(Rule(f"scale({sy},{sx})",
                              lambda g, sy=sy, sx=sx: scale(g, sy, sx),
                              2 + sy + sx, assumptions=1, family="scaling"))
            scaled = lambda g, sy=sy, sx=sx: scale(g, sy, sx)
            mapped = _mapping_rule(pairs, scaled, f"scale({sy},{sx})+color-map",
                                   4 + sy + sx)
            if mapped:
                rules.append(mapped)

    if h1 % h0 == 0 and w1 % w0 == 0:
        ny, nx = h1 // h0, w1 // w0
        if (ny > 1 or nx > 1) and all(
                dimensions(target) == (dimensions(source)[0] * ny,
                                       dimensions(source)[1] * nx)
                and tile(source, ny, nx) == target for source, target in pairs):
            rules.append(Rule(f"tile({ny},{nx})", lambda g, ny=ny, nx=nx: tile(g, ny, nx),
                              3 + ny + nx, assumptions=1, family="tiling"))
            tiled = lambda g, ny=ny, nx=nx: tile(g, ny, nx)
            mapped = _mapping_rule(pairs, tiled, f"tile({ny},{nx})+color-map",
                                   5 + ny + nx)
            if mapped:
                rules.append(mapped)

    mapping = _mapping_rule(pairs, lambda g: g, "global-color-map")
    if mapping:
        rules.append(mapping)

    # Per-color constant translations removed. Relation-conditioned
    # copy/place handles object movement relative to landmarks.
    for radius in (1, 2):
        local_rule = _local_rewrite_rule(pairs, radius)
        if local_rule:
            rules.append(local_rule)
    rules.extend(_count_rules(pairs))
    direct_exact = any(_fits(rule.apply, pairs) for rule in rules)
    search_stats = {"triggered": False,
                    "reason": "direct_exact_hypothesis_exists" if direct_exact
                    else "no_direct_exact_hypothesis"}
    if not direct_exact:
        from .program_search import discover_compositions
        composed, search_stats = discover_compositions(pairs)
        rules.extend(composed)
    return (rules, search_stats) if return_search_stats else rules
