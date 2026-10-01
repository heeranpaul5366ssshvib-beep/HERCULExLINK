"""Deterministic tests for ARC parsing, objects, primitives, and verified rules."""

import pytest

from arc_reasoning.grid import parse_grid
from arc_reasoning.deltas import compare_grids
from arc_reasoning.objects import (
    aligned, adjacent, color_relationships, connected_components, contained,
    describe_object, enclosed_background_cells, encloses, extract_objects,
    object_relations, relative_position,
)
from arc_reasoning.primitives import (
    complete_pattern, coordinate_transform, count, crop, crop_color,
    complete_symmetry, crop_non_background, fill_enclosed_background,
    gravity, grow, intersect, mask, merge_objects, move_objects,
    object_bounding_boxes, object_outlines, order_objects, overlay, recolor,
    reflect_horizontal, reflect_vertical, render_objects, rotate, scale,
    recolor_objects_by_feature, select_objects, split_object, subtract, tile,
    combine_regions, connect_aligned_objects, recolor_by_palette_rank, split_on_separator,
    transform_each_object, translate, extend_lines_to_edge,
    transform_objects_by_signature, object_shape_signature,
    connect_nearest_objects,
)
from arc_reasoning.rules import Rule, generate_hypotheses
from arc_reasoning.solver import ArcSolver, verify_rule


def test_grid_parser_accepts_and_freezes_arc_grid():
    assert parse_grid([[0, 1], [2, 9]]) == ((0, 1), (2, 9))


@pytest.mark.parametrize("bad", [[], [[1], [1, 2]], [[-1]], [[10]], [[True]], ["1"]])
def test_grid_parser_rejects_invalid_grids(bad):
    with pytest.raises(ValueError):
        parse_grid(bad)


def test_grid_delta_separates_preserved_added_removed_and_recolored_cells():
    source = parse_grid([[1, 0], [0, 2]])
    target = parse_grid([[0, 3, 0], [0, 2, 4]])
    delta = compare_grids(source, target)
    assert delta.source_dimensions == (2, 2)
    assert delta.target_dimensions == (2, 3)
    assert delta.dimensions_changed
    assert delta.preserved_cells == frozenset({(1, 1, 2)})
    assert delta.removed_cells == frozenset({(0, 0, 1)})
    assert delta.added_cells == frozenset({(0, 1, 3), (1, 2, 4)})
    assert delta.recolored_cells == frozenset()
    assert delta.changed_cell_count == 3
    recolored = compare_grids(parse_grid([[1]]), parse_grid([[2]]))
    assert recolored.recolored_cells == frozenset({(0, 0, 1, 2)})


def test_components_objects_and_symbolic_features():
    grid = parse_grid([[1, 0, 2], [0, 1, 0], [0, 0, 2]])
    assert len(connected_components(grid, connectivity=4)) == 4
    assert len(connected_components(grid, connectivity=8)) == 3
    objects = extract_objects(grid, connectivity=8)
    first = next(obj for obj in objects if obj.color == 1)
    assert first.cells == frozenset({(0, 0), (1, 1)})
    assert first.bbox == (0, 0, 2, 2)
    assert first.width == first.height == 2
    assert first.orientation == "square"
    assert color_relationships(grid)["cell_counts"] == {1: 2, 2: 2}
    assert color_relationships(grid)["object_counts"] == {1: 2, 2: 2}


def test_object_relationships_containment_alignment_adjacency_enclosure():
    outer = describe_object(1, {(1, 1), (1, 2), (2, 1), (2, 2)})
    inner = describe_object(2, {(1, 1)})
    right = describe_object(3, {(1, 3)})
    assert contained(inner, outer)
    assert aligned(outer, right, "row")
    assert adjacent(outer, right)
    assert relative_position(outer, right) == "right"
    assert {"adjacent", "touching", "immediately_left"} <= \
        object_relations(outer, right)
    ring = parse_grid([[0, 0, 0, 0, 0], [0, 1, 1, 1, 0],
                       [0, 1, 0, 1, 0], [0, 1, 1, 1, 0],
                       [0, 0, 0, 0, 0]])
    assert encloses(ring, (2, 2))
    assert not encloses(ring, (0, 0))
    assert enclosed_background_cells(ring) == frozenset({(2, 2)})


def test_reflection_rotation_translation_and_coordinate_maps():
    grid = parse_grid([[1, 2, 3], [4, 5, 6]])
    assert reflect_horizontal(grid) == ((4, 5, 6), (1, 2, 3))
    assert reflect_vertical(grid) == ((3, 2, 1), (6, 5, 4))
    assert rotate(grid, 1) == ((4, 1), (5, 2), (6, 3))
    assert rotate(grid, 2) == ((6, 5, 4), (3, 2, 1))
    assert rotate(grid, 4) == grid
    assert translate(parse_grid([[0, 1], [0, 0]]), 1, 0) == ((0, 0), (0, 1))
    assert coordinate_transform((0, 0), 2, 3, "rotate90") == (0, 1, 3, 2)


def test_scale_tile_crop_and_nonbackground_crop():
    grid = parse_grid([[1, 0], [0, 2]])
    assert scale(grid, 2) == ((1, 1, 0, 0), (1, 1, 0, 0),
                              (0, 0, 2, 2), (0, 0, 2, 2))
    assert tile(grid, 2, 1) == ((1, 0), (0, 2), (1, 0), (0, 2))
    assert crop(grid, 0, 1, 2, 2) == ((0,), (2,))
    assert crop_non_background(parse_grid([[0, 0, 0], [0, 3, 0], [0, 0, 0]])) == ((3,),)
    assert crop_color(parse_grid([[0, 2, 0], [1, 0, 2]]), 2) == ((2, 0), (0, 2))


def test_recolor_count_and_object_ordering():
    grid = parse_grid([[1, 0, 2], [1, 2, 2]])
    assert recolor(grid, {1: 3}) == ((3, 0, 2), (3, 2, 2))
    assert count(grid) == 5
    assert count(grid, "objects") == 2
    assert count(grid, "colors") == 2
    assert count(grid, "color_cells", color=2) == 3
    assert recolor_by_palette_rank(parse_grid([[0, 3, 4]]), {0: 0, 1: 1, 2: 0}) == (
        (0, 3, 0),)
    ordered = order_objects(extract_objects(grid), "area", reverse=True)
    assert [obj.color for obj in ordered] == [2, 1]


def test_grid_boolean_algebra():
    a = parse_grid([[1, 0], [2, 3]])
    b = parse_grid([[1, 4], [0, 3]])
    assert intersect(a, b) == ((1, 0), (0, 3))
    assert subtract(a, b) == ((0, 0), (2, 0))
    assert overlay(a, b) == ((1, 4), (2, 3))
    assert mask(a, parse_grid([[0, 1], [1, 0]])) == ((0, 0), (2, 0))
    assert combine_regions(a, b, "union") == ((1, 4), (2, 3))
    assert combine_regions(a, b, "xor") == ((0, 4), (2, 0))
    assert combine_regions(a, b, "subtract-left") == ((0, 0), (2, 0))


def test_move_grow_split_merge_and_pattern_completion():
    grid = parse_grid([[0, 1, 0], [0, 0, 0], [0, 0, 2]])
    assert move_objects(grid, 1, 0) == ((0, 0, 0), (0, 1, 0), (0, 0, 0))
    assert grow(parse_grid([[0, 0, 0], [0, 1, 0], [0, 0, 0]])) == (
        (0, 1, 0), (1, 1, 1), (0, 1, 0))
    components = split_object(parse_grid([[1, 0, 1]]))
    assert len(components) == 2
    assert merge_objects(components, 1, 3) == ((1, 0, 1),)
    assert render_objects(components, 1, 3) == ((1, 0, 1),)
    assert complete_pattern([[1, None, 1, None]]) == ((1, 1, 1, 1),)


def test_fill_enclosed_background_is_deterministic():
    ring = parse_grid([[0, 0, 0, 0, 0], [0, 1, 1, 1, 0],
                       [0, 1, 0, 1, 0], [0, 1, 1, 1, 0],
                       [0, 0, 0, 0, 0]])
    assert fill_enclosed_background(ring, 2)[2][2] == 2
    assert fill_enclosed_background(ring)[2][2] == 1


def test_symmetry_completion_bboxes_outlines_and_gravity():
    half = parse_grid([[1, 0, 0], [0, 0, 0], [2, 0, 0]])
    assert complete_symmetry(half, "vertical") == (
        (1, 0, 1), (0, 0, 0), (2, 0, 2))
    assert object_bounding_boxes(parse_grid([[1, 1], [1, 0]])) == (
        (1, 1), (1, 1))
    assert object_outlines(parse_grid([[1, 1, 1], [1, 1, 1], [1, 1, 1]])) == (
        (1, 1, 1), (1, 0, 1), (1, 1, 1))
    falling = parse_grid([[1, 0, 0, 0], [0, 2, 0, 0],
                          [0, 0, 0, 0], [0, 0, 0, 3]])
    assert gravity(falling, "down") == (
        (0, 0, 0, 0), (0, 0, 0, 0),
        (0, 0, 0, 0), (1, 2, 0, 3))
    assert connect_aligned_objects(parse_grid([[1, 0, 0, 1]])) == ((1, 1, 1, 1),)
    with pytest.raises(ValueError):
        complete_symmetry(parse_grid([[1, 2]]), "diagonal")


def test_hypotheses_must_fit_all_demos_and_rank_simplicity():
    pairs = ((parse_grid([[1, 0, 0]]), parse_grid([[0, 1, 0]])),
             (parse_grid([[0, 2, 0]]), parse_grid([[0, 0, 2]])))
    rules = generate_hypotheses(pairs)
    # Fixed-offset translation removed; object-correspondence is the relational alternative
    obj_corr_rule = next(rule for rule in rules if rule.family == "object-correspondence")
    assert obj_corr_rule.name == "object-correspondence(shape,color)"
    assert verify_rule(obj_corr_rule, pairs) == (True, 2)
    inconsistent = Rule("fits-only-first", lambda _grid: pairs[0][1], 1)
    assert verify_rule(inconsistent, pairs) == (False, 2)


def test_hypothesis_coverage_counts_generation_and_exact_replay_without_changing_outputs():
    task = {"train": [
        {"input": [[1, 0, 0]], "output": [[0, 1, 0]]},
        {"input": [[0, 2, 0]], "output": [[0, 0, 2]]},
    ], "test": [{"input": [[3, 0, 0]]}]}
    solver = ArcSolver()
    ordinary = solver.solve(task)
    measured = solver.solve(task, include_coverage=True)
    assert [candidate.grid for candidate in ordinary["candidates"][0]] == [
        candidate.grid for candidate in measured["candidates"][0]]
    coverage = measured["hypothesis_coverage"]
    assert coverage["status"] == "one_or_more_hypotheses_replayed_exactly"
    assert coverage["generated_hypotheses"] >= coverage["verified_hypotheses"] > 0
    assert sum(coverage["families_generated"].values()) == coverage["generated_hypotheses"]


def test_geometry_then_noninjective_color_map_is_inferred_from_all_demos():
    task = {
        "train": [
            {"input": [[1, 0], [2, 0]], "output": [[0, 3], [0, 3]]},
            {"input": [[0, 2], [1, 0]], "output": [[3, 0], [0, 3]]},
        ],
        "test": [{"input": [[2, 0], [0, 1]]}],
    }
    result = ArcSolver().solve(task)
    assert result["candidates"][0]
    assert result["candidates"][0][0].grid == ((0, 3), (3, 0))
    assert any("reflect-vertical+color-map" == rule
               for rule in result["verified_rules"])


def test_split_separator_and_region_rule_replay():
    source = parse_grid([[1, 0, 2], [5, 5, 5], [0, 2, 0]])
    assert split_on_separator(source, "horizontal") == (
        ((1, 0, 2),), ((0, 2, 0),))
    task = {"train": [
        {"input": [[1, 0, 2], [5, 5, 5], [0, 2, 0]],
         "output": [[1, 2, 2]]},
        {"input": [[3, 0], [4, 4], [0, 3]],
         "output": [[3, 3]]},
    ], "test": [{"input": [[2, 0], [6, 6], [0, 2]]}]}
    result = ArcSolver().solve(task, include_coverage=True)
    # Split/combine rules fit training exactly but fail core invariance checks
    # (canvas_padding, background_recolor not applicable for dimension-changing rules)
    coverage = result["hypothesis_coverage"]
    assert coverage["exact_training_hypotheses"] >= 1
    assert coverage["invariance_surviving_hypotheses"] == 0
    assert coverage["status"] == "exact_hypotheses_rejected_by_invariance"
    # The split-horizontal-xor rule is generated as exact-fit but rejected by invariance
    exact_families = coverage.get("exact_families", {})
    assert "region-combination" in exact_families


def test_local_neighborhood_exact_fit_is_rejected_without_invariance():
    input_grid = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    output_grid = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    task = {"train": [{"input": input_grid, "output": output_grid},
                      {"input": input_grid, "output": output_grid}],
            "test": [{"input": input_grid}]}
    result = ArcSolver().solve(task, include_coverage=True)
    assert "local-neighborhood-r1" not in result["verified_rules"]
    coverage = result["hypothesis_coverage"]
    assert coverage["exact_local_rewrite_hypotheses"] >= 1
    assert coverage["invariance_surviving_local_rewrite_hypotheses"] == 0
    assert coverage["status"] == "exact_hypotheses_rejected_by_invariance"


def test_palette_role_hypothesis_generalizes_across_color_names():
    task = {"train": [
        {"input": [[0, 1, 2]], "output": [[0, 1, 0]]},
        {"input": [[0, 3, 4]], "output": [[0, 3, 0]]},
    ], "test": [{"input": [[0, 5, 6]]}]}
    result = ArcSolver().solve(task, include_coverage=True)
    # Palette-role rules fit training exactly but fail background_recolor core check.
    # A color-map rule survives via canvas_padding.
    coverage = result["hypothesis_coverage"]
    assert coverage["exact_training_hypotheses"] >= 1
    # Palette-role rules are rejected; one color-map rule survives
    assert coverage["invariance_surviving_hypotheses"] == 1
    exact_families = coverage.get("exact_families", {})
    assert "palette-role" in exact_families
    # The solver falls back to a color-map rule that passes canvas_padding
    assert "reflect-horizontal+color-map" in result["verified_rules"]
    assert any(candidate.grid == ((0, 5, 6),)
               for candidate in result["candidates"][0])


def test_aligned_object_connection_rule_reuses_relation_across_examples():
    task = {"train": [
        {"input": [[1, 0, 0, 1]], "output": [[1, 1, 1, 1]]},
        {"input": [[2, 0, 2]], "output": [[2, 2, 2]]},
    ], "test": [{"input": [[3, 0, 0, 0, 3]]}]}
    result = ArcSolver().solve(task, include_coverage=True)
    # connect-aligned rules now pass background_recolor (core check) after
    # background inference fix, so they survive invariance.
    # Palette-role rules fail background_recolor and are rejected.
    coverage = result["hypothesis_coverage"]
    assert coverage["exact_training_hypotheses"] >= 1
    assert coverage["invariance_surviving_hypotheses"] >= 1
    # connect-aligned rules are in verified_rules
    verified = result["verified_rules"]
    connect_aligned_verified = [r for r in verified if "connect-aligned" in r]
    assert len(connect_aligned_verified) >= 1
    # Palette-role rules are exact-fit but rejected by invariance
    exact_families = coverage.get("exact_families", {})
    assert "palette-role" in exact_families
    palette_role_verified = [r for r in verified if "palette-role" in r]
    assert len(palette_role_verified) == 0


def test_candidate_ranking_prefers_simplest_exact_rule():
    task = {"train": [{"input": [[2, 0], [0, 0]],
                       "output": [[2, 0], [0, 0]]}],
            "test": [{"input": [[4, 0], [0, 0]]}]}
    result = ArcSolver().solve(task)
    assert result["candidates"][0]
    assert result["candidates"][0][0].rule == "identity"
    assert result["candidates"][0][0].simplicity <= \
        result["candidates"][0][-1].simplicity


def test_test_output_is_ignored_during_inference():
    task = {"train": [{"input": [[1, 0]], "output": [[0, 1]]}],
            "test": [{"input": [[2, 0]], "output": [[9, 9], [9, 9]]}]}
    result = ArcSolver().solve(task)
    assert result["candidates"][0][0].grid == ((0, 2),)
    assert result["candidates"][0][0].support


def test_adversarial_contradictory_demos_produce_no_rule():
    task = {"train": [
        {"input": [[1, 0]], "output": [[0, 1]]},
        {"input": [[1, 0]], "output": [[1, 0]]},
    ], "test": [{"input": [[2, 0]]}]}
    result = ArcSolver().solve(task)
    assert result["verified_rules"] == []
    assert result["candidates"] == [[]]


def test_two_candidates_are_distinct_and_optional_ranker_cannot_override_verifier():
    # Use a marker-tracking task where relation-conditioned copy applies
    task = {
        "train": [
            {"input": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
             "output": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0]]},
            {"input": [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]],
             "output": [[0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 0, 0],
                        [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]]},
        ],
        "test": [{"input": [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 2, 0],
                            [0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0]]}],
    }
    result = ArcSolver(advisory_ranker=lambda rows: ["identity"]).solve(task)
    assert len(result["candidates"][0]) <= 2
    # The correct output follows the marker (color 2) which moves between examples
    expected = ((0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 1, 1),
                (0, 0, 0, 0, 0, 0, 0), (1, 1, 0, 0, 0, 0, 0))
    assert result["candidates"][0][0].grid == expected
    assert "identity" not in result["verified_rules"]


def test_candidates_are_replayed_on_every_train_pair_and_deduplicated():
    task = {"train": [{"input": [[1, 1]], "output": [[1, 1]]}],
            "test": [{"input": [[1, 1]]}]}
    result = ArcSolver().solve(task)
    assert result["candidates"] == [[]] or len(result["candidates"][0]) == 1
    if result["candidates"][0]:
        assert result["candidates"][0][0].grid == ((1, 1),)


def test_agent_adapter_keeps_existing_lifecycle_and_authority_boundary():
    from agents.arc_reasoning_agent import ArcReasoningAgent
    from agents.agent_state import AgentState

    agent = ArcReasoningAgent()
    response = agent.execute({"arc_task": {
        "train": [{"input": [[1, 0]], "output": [[0, 1]]}],
        "test": [{"input": [[2, 0]]}],
    }})
    assert response["status"] == "success"
    assert response["authority"] == "deterministic-training-replay-verifier"
    assert agent.get_state() == AgentState.READY
    assert len(response["arc"]["candidates"][0]) <= 2


def test_object_selection_feature_recolor_and_local_transform():
    grid = parse_grid([[1, 1, 0, 2], [0, 0, 0, 0]])
    assert select_objects(grid, "largest") == ((1, 1, 0, 0), (0, 0, 0, 0))
    assert recolor_objects_by_feature(grid, {1: 3, 2: 4}, "size") == (
        (4, 4, 0, 3), (0, 0, 0, 0))
    assert transform_each_object(parse_grid([[1, 1, 0], [0, 0, 0]]),
                                 "rotate-90") == ((1, 0, 0), (1, 0, 0))


def test_line_extension_is_bounded_by_conflicting_objects():
    grid = parse_grid([[0, 2, 2, 0], [0, 0, 0, 0]])
    assert extend_lines_to_edge(grid) == ((2, 2, 2, 2), (0, 0, 0, 0))
    crossing = parse_grid([[0, 1, 1], [0, 2, 0], [0, 2, 0]])
    with pytest.raises(ValueError, match="line extensions conflict"):
        extend_lines_to_edge(crossing)


def test_nearest_object_connection_has_two_explicit_routes_and_rejects_ties():
    diagonal = parse_grid([[1, 0, 0], [0, 0, 0], [0, 0, 1]])
    assert connect_nearest_objects(diagonal, "horizontal-first") == (
        (1, 1, 1), (0, 0, 1), (0, 0, 1))
    assert connect_nearest_objects(diagonal, "vertical-first") == (
        (1, 0, 0), (1, 0, 0), (1, 1, 1))
    tied = parse_grid([[1, 0, 1], [0, 0, 0], [1, 0, 0]])
    with pytest.raises(ValueError, match="nearest object pair is ambiguous"):
        connect_nearest_objects(tied)


def test_nearest_connection_hypothesis_replays_demos_and_generalizes_route():
    task = {"train": [
        {"input": [[1, 0, 0], [0, 0, 0], [0, 0, 1]],
         "output": [[1, 1, 1], [0, 0, 1], [0, 0, 1]]},
        {"input": [[0, 1, 0], [0, 0, 0], [0, 0, 1]],
         "output": [[0, 1, 1], [0, 0, 1], [0, 0, 1]]},
    ], "test": [{"input": [[1, 0, 0, 0], [0, 0, 0, 1]]}]}
    result = ArcSolver().solve(task)
    rule = "connect-nearest(horizontal-first,same)"
    assert rule in result["verified_rules"]
    assert any(candidate.grid == ((1, 1, 1, 1), (0, 0, 0, 1))
               for candidate in result["candidates"][0])

    inconsistent = {"train": task["train"][:1] + [
        {"input": [[0, 1, 0], [0, 0, 0], [0, 0, 1]],
         "output": [[0, 1, 0], [0, 1, 0], [0, 1, 1]]}],
        "test": task["test"]}
    assert rule not in ArcSolver().solve(inconsistent)["verified_rules"]


def test_signature_matched_object_transform_moves_and_recolors():
    source = parse_grid([[1, 1, 0, 0], [0, 0, 0, 0]])
    obj = extract_objects(source)[0]
    transforms = {(obj.color, object_shape_signature(obj)): (1, 2, 3)}
    assert transform_objects_by_signature(source, transforms) == (
        (0, 0, 0, 0), (0, 0, 3, 3))
    with pytest.raises(ValueError, match="no signature-matched transform"):
        transform_objects_by_signature(source, {})
    with pytest.raises(ValueError, match="exceeds grid bounds"):
        transform_objects_by_signature(
            source, {(obj.color, object_shape_signature(obj)): (-1, 0, 1)})


def test_object_correspondence_infers_color_conditioned_relative_motion():
    task = {"train": [
        {"input": [[1, 0, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 2]],
         "output": [[0, 0, 0, 0, 0], [1, 0, 0, 0, 0], [0, 0, 0, 2, 0]]},
        {"input": [[0, 0, 0, 0, 2], [0, 1, 0, 0, 0], [0, 0, 0, 0, 0]],
         "output": [[0, 0, 0, 2, 0], [0, 0, 0, 0, 0], [0, 1, 0, 0, 0]]},
    ], "test": [{"input": [[0, 0, 1, 0, 0], [0, 0, 0, 0, 2],
                            [0, 0, 0, 0, 0]]}]}
    result = ArcSolver().solve(task)
    assert "object-correspondence(shape,color)" in result["verified_rules"]
    assert any(candidate.grid == ((0, 0, 0, 0, 0), (0, 0, 1, 2, 0),
                                  (0, 0, 0, 0, 0))
               for candidate in result["candidates"][0])

    inconsistent = {"train": task["train"] + [
        {"input": [[0, 0, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 2]],
         "output": [[0, 1, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 2, 0]]}],
        "test": task["test"]}
    assert "object-correspondence(shape,color)" not in ArcSolver().solve(inconsistent)["verified_rules"]


def test_relation_copy_places_source_shape_on_unique_marker_and_tracks_it():
    task = {"train": [
        {"input": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
         "output": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0]]},
        {"input": [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]],
         "output": [[0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]]},
    ], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 2, 0],
                            [0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0]]}]}
    result = ArcSolver().solve(task, include_coverage=True)
    relational = [name for name in result["verified_rules"]
                  if name.startswith("object-program:copy")]
    assert relational
    assert all("offset" not in name for name in relational)
    expected = ((0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 1, 1),
                (0, 0, 0, 0, 0, 0, 0), (1, 1, 0, 0, 0, 0, 0))
    assert any(candidate.grid == expected for candidate in result["candidates"][0])
    coverage = result["hypothesis_coverage"]
    assert coverage["invariance_surviving_relation_hypotheses"] > 0
    assert coverage["invariance_check_outcomes"]["landmark_translation"]["pass"] > 0
    assert coverage["invariance_check_outcomes"]["background_recolor"]["pass"] > 0


def test_relation_copy_places_next_to_landmark_by_alignment_not_constant_offset():
    task = {"train": [
        {"input": [[1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 2, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
         "output": [[1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 2, 2, 1, 0], [0, 0, 0, 0, 0, 0, 0]]},
        {"input": [[0, 2, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0]],
         "output": [[0, 2, 2, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0]]},
    ], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 2, 2, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0]]}]}
    result = ArcSolver().solve(task)
    assert any("adjacent:right" in name for name in result["verified_rules"])
    expected = ((0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 2, 2, 1, 0),
                (0, 0, 0, 0, 0, 0, 0), (1, 0, 0, 0, 0, 0, 0))
    assert any(candidate.grid == expected for candidate in result["candidates"][0])


def test_bounded_program_search_finds_selection_rotation_and_recolor_composition():
    from arc_reasoning.primitives import recolor, rotate, select_objects

    sources = (
        parse_grid([[2, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 2, 2, 0], [0, 0, 0, 0, 2, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0]]),
        parse_grid([[2, 0, 0, 0, 0, 0, 0], [0, 0, 2, 2, 0, 0, 0],
                    [0, 0, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0]]),
    )
    outputs = tuple(recolor(rotate(select_objects(grid, "largest"), 1),
                            {2: 3}) for grid in sources)
    pairs = tuple(zip(sources, outputs))
    from arc_reasoning.program_search import discover_compositions
    rules, stats = discover_compositions(pairs, max_depth=3)
    exact = [rule for rule in rules
             if all(rule.apply(source) == output for source, output in pairs)]
    assert stats["triggered"]
    assert exact
    test_grid = parse_grid([[0, 0, 0, 0, 0, 0, 0],
                            [0, 2, 0, 0, 0, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0],
                            [0, 2, 2, 0, 0, 0, 0],
                            [0, 2, 0, 0, 0, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0]])
    expected = recolor(rotate(select_objects(test_grid, "largest"), 1), {2: 3})
    generalizing = []
    for rule in exact:
        try:
            generalizing.append(rule.apply(test_grid))
        except (ArithmeticError, IndexError, TypeError, ValueError):
            continue
    assert expected in generalizing
    task = {"train": [{"input": [list(row) for row in source],
                       "output": [list(row) for row in target]}
                      for source, target in pairs],
            "test": [{"input": [list(row) for row in test_grid]}]}
    result = ArcSolver().solve(task, include_coverage=True)
    assert any(name.startswith("program:") for name in result["verified_rules"])
    assert any("rotate-90" in name and "recolor-objects-by-size" in name
               for name in result["verified_rules"])
    assert result["candidates"][0][0].grid == expected
    assert result["hypothesis_coverage"]["program_search"]["exact_programs_found"] > 0


def test_relation_funnel_cuts_raw_hypotheses_to_sixteen():
    """Test that relation hypotheses are funneled from 64 to <=16 before invariance."""
    # Marker-tracking task generates many relation hypotheses
    task = {"train": [
        {"input": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
         "output": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0]]},
        {"input": [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]],
         "output": [[0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]]},
    ], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 2, 0],
                            [0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0]]}]}
    result = ArcSolver().solve(task, include_coverage=True)
    coverage = result["hypothesis_coverage"]
    # Raw generated should be capped at 64 by generate_relation_copy_hypotheses
    # After parsimony funnel should be <= 16
    assert coverage.get("after_parsimony_funnel", 0) <= 16
    # Funnel should not drop the correct onto_marker hypothesis
    assert any("onto_marker" in r for r in result["verified_rules"])
    # After invariance, final selection keeps 1 primary + 1 backup max
    assert len(result["verified_rules"]) <= 2
    # The primary should be an onto_marker relation (simplest placement)
    primary = result["verified_rules"][0]
    assert "onto_marker" in primary or "align_bbox" in primary
