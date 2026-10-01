"""Bounded, evidence-guided composition search for ARC grid programs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .grid import Grid, dimensions
from .deltas import compare_grids
from .objects import extract_objects
from .primitives import (
    combine_regions, complete_symmetry, connect_aligned_objects,
    connect_nearest_objects, crop_color, crop_non_background,
    extend_lines_to_edge, fill_enclosed_background, gravity,
    object_bounding_boxes, object_feature, object_outlines,
    recolor_objects_by_feature, reflect_horizontal, reflect_vertical, rotate,
    scale, select_objects, split_on_separator, tile, transform_each_object,
)
from .rules import (
    Rule, _local_rewrite_rule, _mapping_rule,
    _object_correspondence_rule, _palette_rank_rule,
)


Transform = Callable[[Grid], Grid]


@dataclass(frozen=True)
class Operator:
    name: str
    apply: Transform
    complexity: int
    assumptions: int
    family: str
    known_colors: tuple[int, ...] = ()
    relation_predicates: tuple[str, ...] = ()
    local_writes: int = 0


@dataclass(frozen=True)
class Node:
    outputs: tuple[Grid, ...]
    program: tuple[Operator, ...]

    @property
    def cost(self) -> int:
        return sum(operator.complexity for operator in self.program)

    @property
    def assumptions(self) -> int:
        return sum(operator.assumptions for operator in self.program)

    @property
    def name(self) -> str:
        return " -> ".join(operator.name for operator in self.program)


def _operator_library(pairs: tuple[tuple[Grid, Grid], ...]) -> list[Operator]:
    operators: list[Operator] = []
    deltas = tuple(compare_grids(source, target) for source, target in pairs)
    dimensions_change = any(delta.dimensions_changed for delta in deltas)
    same_dimensions = all(not delta.dimensions_changed for delta in deltas)
    has_additions = any(delta.added_cells for delta in deltas)
    has_changes = any(delta.changed_cell_count for delta in deltas)
    selection_plausible = any(
        len(extract_objects(target)) < len(extract_objects(source)) or
        sum(value != 0 for row in target for value in row) <
        sum(value != 0 for row in source for value in row)
        for source, target in pairs)
    palette_reduced = any(
        {value for row in target for value in row} <
        {value for row in source for value in row}
        for source, target in pairs)

    def add(name, apply, complexity=2, assumptions=1, family="primitive",
            known_colors=(), relation_predicates=(), local_writes=0):
        operators.append(Operator(name, apply, complexity, assumptions,
                                  family, tuple(sorted(set(known_colors))),
                                  tuple(relation_predicates), local_writes))

    core_geometry = (
        ("reflect-horizontal", reflect_horizontal, 2),
        ("reflect-vertical", reflect_vertical, 2),
        ("reflect-both-axes", lambda g: reflect_vertical(reflect_horizontal(g)), 3),
        ("rotate-90", lambda g: rotate(g, 1), 2),
        ("rotate-180", lambda g: rotate(g, 2), 2),
        ("rotate-270", lambda g: rotate(g, 3), 2),
    )
    for name, fn, cost in core_geometry:
        add(name, fn, cost, family="grid-transform")
    if dimensions_change:
        add("crop-non-background", crop_non_background, 2,
            family="grid-transform")
    if has_additions:
        for name, fn, cost in (
                ("fill-enclosed", fill_enclosed_background, 3),
                ("fill-object-bboxes", object_bounding_boxes, 3),
                ("object-outlines", object_outlines, 3),
                ("extend-lines-to-edge", extend_lines_to_edge, 4)):
            add(name, fn, cost, family="object-construction")

    if has_additions:
        for axis in ("vertical", "horizontal", "diagonal", "antidiagonal"):
            add(f"complete-symmetry({axis})",
                lambda g, axis=axis: complete_symmetry(g, axis), 3,
                family="symmetry")
    if same_dimensions and has_changes:
        for direction in ("up", "down", "left", "right"):
            add(f"gravity-{direction}",
                lambda g, direction=direction: gravity(g, direction), 4,
                family="object-movement")
    if selection_plausible:
        for selector in ("largest", "smallest", "unique-size", "unique-shape",
                         "most-frequent-color", "least-frequent-color", "symmetric",
                         "asymmetric", "horizontal", "vertical", "square", "point",
                         "wide", "tall"):
            add(f"select-objects({selector})",
                lambda g, selector=selector: select_objects(g, selector), 3,
                family=f"object-selection-{selector}")
    if same_dimensions:
        for operation in ("reflect-horizontal", "reflect-vertical", "rotate-90",
                          "rotate-180", "rotate-270"):
            add(f"transform-each-object({operation})",
                lambda g, operation=operation: transform_each_object(g, operation),
                4, family="object-transform")
    if has_additions:
        for policy in ("same", "first", "second"):
            add(f"connect-aligned({policy})",
                lambda g, policy=policy: connect_aligned_objects(g, policy),
                5, assumptions=2, family="object-relations")
            for route in ("horizontal-first", "vertical-first"):
                add(f"connect-nearest({route},{policy})",
                    lambda g, route=route, policy=policy:
                    connect_nearest_objects(g, route, policy),
                    7, assumptions=3, family="object-relations")

        # Relation-conditioned copy/place is a terminal hypothesis, not an
        # intermediate operator. It is generated only in _terminal_rules.

    colors = sorted({value for source, _ in pairs for row in source for value in row
                     if value != 0})
    if selection_plausible or palette_reduced:
        for color in colors:
            add(f"keep-color({color})",
                lambda g, color=color: tuple(tuple(value if value == color else 0
                                                    for value in row) for row in g),
                2, family="object-selection", known_colors=(color,))
            add(f"crop-color({color})",
                lambda g, color=color: crop_color(g, color), 3,
                family="object-selection", known_colors=(color,))
    if has_additions:
        for color in colors:
            add(f"fill-holes({color})",
                lambda g, color=color: fill_enclosed_background(g, color), 3,
                family="topology", known_colors=(color,))

    # Dimension factors are capped; the search only uses factors visible in
    # demonstration input/output dimensions or the common small ARC factors.
    factors = set()
    if dimensions_change:
        for source, target in pairs:
            sh, sw = dimensions(source)
            th, tw = dimensions(target)
            if sh and th % sh == 0 and 1 < th // sh <= 4:
                factors.add(th // sh)
            if sw and tw % sw == 0 and 1 < tw // sw <= 4:
                factors.add(tw // sw)
        factors.update({2, 3})
    for sy in sorted(factors):
        for sx in sorted(factors):
            if sy * sx > 9:
                continue
            add(f"scale({sy},{sx})", lambda g, sy=sy, sx=sx: scale(g, sy, sx),
                2 + sy + sx, family="scaling")
            add(f"tile({sy},{sx})", lambda g, sy=sy, sx=sx: tile(g, sy, sx),
                3 + sy + sx, family="tiling")

    if dimensions_change:
      for axis in ("horizontal", "vertical"):
        for operation in ("union", "intersection", "xor",
                          "subtract-left", "subtract-right"):
            def combine(grid: Grid, axis=axis, operation=operation) -> Grid:
                regions = split_on_separator(grid, axis)
                if len(regions) != 2:
                    raise ValueError("expected two regions around a separator")
                return combine_regions(regions[0], regions[1], operation)
            add(f"split-{axis}-{operation}", combine, 4,
                assumptions=2, family="region-combination")
    return operators


def _grid_loss(outputs: tuple[Grid, ...], targets: tuple[Grid, ...]) -> int:
    total = 0
    for output, target in zip(outputs, targets):
        oh, ow = dimensions(output)
        th, tw = dimensions(target)
        total += 30 * (abs(oh - th) + abs(ow - tw))
        total += sum(output[row][col] != target[row][col]
                     for row in range(min(oh, th))
                     for col in range(min(ow, tw)))
        out_counts = Counter(value for row in output for value in row if value)
        target_counts = Counter(value for row in target for value in row if value)
        total += 2 * sum(abs(out_counts[color] - target_counts[color])
                         for color in set(out_counts) | set(target_counts))
    return total


def _feature_recolor_rule(pairs: tuple[tuple[Grid, Grid], ...]) -> Rule | None:
    for feature in ("size", "shape", "orientation", "symmetry", "dimensions"):
        mapping = {}
        consistent = True
        for source, target in pairs:
            if dimensions(source) != dimensions(target):
                consistent = False
                break
            for obj in extract_objects(source):
                colors = {target[row][col] for row, col in obj.cells}
                if len(colors) != 1:
                    consistent = False
                    break
                key, color = object_feature(obj, feature), next(iter(colors))
                if key in mapping and mapping[key] != color:
                    consistent = False
                    break
                mapping[key] = color
            if not consistent:
                break
        if consistent and mapping:
            transform = lambda grid, mapping=mapping, feature=feature: \
                recolor_objects_by_feature(grid, mapping, feature)
            return Rule(f"recolor-objects-by-{feature}", transform, 4,
                        assumptions=1, family="object-recolor")
    return None


def _terminal_rules(outputs: tuple[Grid, ...], targets: tuple[Grid, ...]) -> list[Rule]:
    pairs = tuple(zip(outputs, targets))
    terminals = []
    mapping = _mapping_rule(pairs, lambda grid: grid, "global-color-map", 2)
    if mapping:
        terminals.append(mapping)
    for measure in ("cells", "objects"):
        palette = _palette_rank_rule(pairs, measure, lambda grid: grid,
                                     f"palette-role-{measure}")
        if palette:
            terminals.append(palette)
    for factory in (_feature_recolor_rule, _object_correspondence_rule):
        rule = factory(pairs)
        if rule:
            terminals.append(rule)
    from .relations import generate_relation_copy_hypotheses
    # Limit relation hypotheses in search to avoid combinatorial explosion.
    # They are end-to-end rules; using many as terminals bloats search.
    terminals.extend(generate_relation_copy_hypotheses(pairs, max_hypotheses=16))
    for radius in (1, 2):
        local = _local_rewrite_rule(pairs, radius)
        if local:
            terminals.append(local)
    return terminals


def _compose_rule(program: tuple[Operator, ...],
                  terminal: Rule | None = None) -> Rule:
    operations = tuple(program)
    names = [op.name for op in operations]
    if terminal:
        names.append(terminal.name)
    complexity = sum(op.complexity for op in operations)
    assumptions = sum(op.assumptions for op in operations)
    known_colors = {color for op in operations for color in op.known_colors}
    relation_predicates = tuple(dict.fromkeys(
        predicate for op in operations for predicate in op.relation_predicates))
    local_writes = sum(op.local_writes for op in operations)
    family = "program-search"
    if terminal:
        complexity += terminal.complexity
        assumptions += terminal.assumptions
        known_colors.update(terminal.known_colors)
        relation_predicates += tuple(predicate for predicate in
                                     terminal.relation_predicates
                                     if predicate not in relation_predicates)
        local_writes += terminal.local_writes

    def apply(grid: Grid, operations=operations, terminal=terminal) -> Grid:
        result = grid
        for op in operations:
            result = op.apply(result)
        return terminal.apply(result) if terminal else result

    return Rule("program: " + " -> ".join(names), apply,
                complexity, assumptions, family=family,
                structural_coverage=len(names),
                known_colors=tuple(sorted(known_colors)),
                relation_predicates=relation_predicates,
                local_writes=local_writes)


def _select_beam(nodes: list[Node], targets: tuple[Grid, ...],
                 width: int) -> list[Node]:
    unique: dict[tuple[Grid, ...], Node] = {}
    for node in nodes:
        previous = unique.get(node.outputs)
        if previous is None or (node.cost, node.assumptions, node.name) < (
                previous.cost, previous.assumptions, previous.name):
            unique[node.outputs] = node
    ordered = sorted(unique.values(), key=lambda node: (
        _grid_loss(node.outputs, targets), node.cost,
        node.assumptions, node.name))
    family_counts: Counter[str] = Counter()
    selected = []
    family_limit = max(3, width // 4)
    for node in ordered:
        family = node.program[-1].family if node.program else "input"
        if family_counts[family] >= family_limit:
            continue
        selected.append(node)
        family_counts[family] += 1
        if len(selected) == width:
            break
    return selected


def discover_compositions(
        pairs: tuple[tuple[Grid, Grid], ...],
        max_depth: int = 3,
        beam_width: int = 32,
        max_returned: int = 12) -> tuple[list[Rule], dict]:
    """Search short typed-ish grid programs, then leave acceptance to replay."""
    started = perf_counter()
    targets = tuple(target for _, target in pairs)
    source_state = tuple(source for source, _ in pairs)
    operators = _operator_library(pairs)
    beam = [Node(source_state, ())]
    visited_beam_states = {source_state}
    stats = {"triggered": True, "max_depth": max_depth,
             "depth_reached": 0,
             "beam_width": beam_width, "operator_count": len(operators),
             "state_expansions": 0, "candidate_states_by_depth": {},
             "unique_states_by_depth": {},
             "exact_programs_by_depth": {},
             "exact_programs_found": 0, "emitted_partial_programs": 0,
             "termination": "max_depth", "terminated_on_exact": False}
    all_exact_rules: dict[str, Rule] = {}

    for depth in range(1, max_depth + 1):
        stats["depth_reached"] = depth
        next_by_family: dict[str, dict[tuple[Grid, ...], Node]] = {}
        exact_rules = []
        family_limit = max(2, beam_width // 4)
        for node in beam:
            if len(node.program) + 1 <= max_depth:
                for terminal in _terminal_rules(node.outputs, targets):
                    try:
                        predicted = tuple(terminal.apply(grid) for grid in node.outputs)
                    except (ArithmeticError, IndexError, TypeError, ValueError):
                        continue
                    if predicted == targets:
                        program = _compose_rule(node.program, terminal)
                        if program.name not in all_exact_rules:
                            exact_rules.append(program)
                            all_exact_rules[program.name] = program
            if len(node.program) >= max_depth:
                continue
            for operator in operators:
                stats["state_expansions"] += 1
                try:
                    outputs = tuple(operator.apply(grid) for grid in node.outputs)
                except (ArithmeticError, IndexError, TypeError, ValueError):
                    continue
                if outputs == node.outputs:
                    continue
                program = node.program + (operator,)
                if outputs == targets:
                    candidate = _compose_rule(program)
                    if candidate.name not in all_exact_rules:
                        exact_rules.append(candidate)
                        all_exact_rules[candidate.name] = candidate
                    continue
                if outputs in visited_beam_states:
                    continue
                candidate = Node(outputs, program)
                family_nodes = next_by_family.setdefault(operator.family, {})
                previous = family_nodes.get(outputs)
                if previous is None or (candidate.cost, candidate.assumptions,
                                        candidate.name) < (
                        previous.cost, previous.assumptions, previous.name):
                    family_nodes[outputs] = candidate
                # Keep a small per-family reservoir while expanding instead
                # of retaining every beam x operator state until layer end.
                if len(family_nodes) > 2 * family_limit:
                    ordered_family = sorted(family_nodes.values(), key=lambda item: (
                        _grid_loss(item.outputs, targets), item.cost,
                        item.assumptions, item.name))
                    family_nodes.clear()
                    family_nodes.update((item.outputs, item)
                                        for item in ordered_family[:family_limit])
        if exact_rules:
            stats["exact_programs_by_depth"][str(depth)] = len(exact_rules)
        next_nodes = [node for family_nodes in next_by_family.values()
                      for node in family_nodes.values()]
        stats["candidate_states_by_depth"][str(depth)] = len(next_nodes)
        beam = _select_beam(next_nodes, targets, beam_width)
        visited_beam_states.update(node.outputs for node in beam)
        stats["unique_states_by_depth"][str(depth)] = len(beam)
        if not beam:
            stats["termination"] = ("frontier_exhausted_after_exact"
                                     if all_exact_rules else "empty_frontier")
            break

    if all_exact_rules:
        exact_rules = sorted(all_exact_rules.values(), key=lambda rule: (
            rule.complexity, rule.assumptions, -rule.structural_coverage,
            rule.name))
        stats["exact_programs_found"] = len(exact_rules)
        stats["first_exact_depth"] = min(map(int,
                                             stats["exact_programs_by_depth"]))
        stats["terminated_on_exact"] = True
        if stats["termination"] == "max_depth":
            stats["termination"] = "max_depth_after_exact"
        stats["elapsed_seconds"] = round(perf_counter() - started, 6)
        return exact_rules[:max_returned], stats

    partial_rules = [_compose_rule(node.program) for node in beam if node.program]
    partial_rules.sort(key=lambda rule: (rule.complexity, rule.assumptions,
                                        rule.name))
    stats["emitted_partial_programs"] = min(len(partial_rules), max_returned)
    stats["elapsed_seconds"] = round(perf_counter() - started, 6)
    return partial_rules[:max_returned], stats
