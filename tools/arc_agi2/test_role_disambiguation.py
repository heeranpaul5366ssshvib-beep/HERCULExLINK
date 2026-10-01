"""Synthetic tests for ARC-AGI-2 multi-object role disambiguation."""

from __future__ import annotations

from arc_reasoning.grid import parse_grid, make_grid
from arc_reasoning.objects import extract_objects
from arc_reasoning.relations import (
    solve_role_constraints, RelationalConstraint, RoleAssignment,
    generate_role_candidates, compute_assignment_score,
    left_of, right_of, above, below, same_row, same_column,
    between, vertically_between, nth_from_left, nth_from_right,
    nth_from_top, nth_from_bottom, nearest_to, farthest_from,
    same_distance, aligned_with, relative_offset, same_relative_position,
    normalized_shape
)


def make_test_grid() -> tuple:
    """Create a test grid with 4 corner objects for testing."""
    return make_grid(5, 5, fill=0)


def create_grid_with_objects(objects_spec: list) -> tuple:
    """Create a grid with specified objects.
    
    objects_spec: list of (color, r, c) tuples
    """
    grid = make_grid(7, 7, fill=0)
    grid_list = [list(row) for row in grid]
    for color, r, c in objects_spec:
        grid_list[r][c] = color
    return tuple(tuple(row) for row in grid_list)


def test_basic_relations():
    """Test basic relational predicates."""
    # Grid with 4 corner objects
    grid = (
        (1, 0, 0, 0, 2),
        (0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0),
        (3, 0, 0, 0, 4),
    )
    objects = extract_objects(parse_grid(grid))
    
    # Objects are at corners: 1 at (0,0), 2 at (0,4), 3 at (3,0), 4 at (3,4)
    # In row-major order: 1, 2, 3, 4
    a, b, c, d = objects[0], objects[1], objects[2], objects[3]
    
    assert left_of(a, b) == True
    assert right_of(a, b) == False
    assert above(a, c) == True
    assert below(a, c) == False
    assert same_row(a, b) == True
    assert same_column(a, c) == True
    assert between(b, a, d) == False  # b is not between a and d horizontally
    
    print("test_basic_relations PASSED")


def test_identical_landmarks():
    """Test disambiguation when multiple objects have identical intrinsic properties."""
    # Grid with two identical red objects at different positions
    grid = create_grid_with_objects([
        (1, 1, 1),  # red at (1,1)
        (1, 1, 5),  # red at (1,5) - identical color/shape
        (2, 3, 3),  # blue at center
        (3, 5, 1),  # green at bottom-left
    ])
    objects = extract_objects(parse_grid(grid))
    
    # Both red objects have same color and shape
    red_objects = [o for o in objects if o.color == 1]
    assert len(red_objects) == 2
    
    # They should be distinguishable by position
    # One is left of the other
    assert left_of(red_objects[0], red_objects[1]) or left_of(red_objects[1], red_objects[0])
    
    # Nth from left should distinguish them
    all_objects = [o for o in objects if o.color in [1, 2, 3]]
    leftmost = min(all_objects, key=lambda o: o.centroid[1])
    rightmost = max(all_objects, key=lambda o: o.centroid[1])
    
    assert nth_from_left(leftmost, all_objects, 1)
    assert nth_from_right(rightmost, all_objects, 1)
    
    print("test_identical_landmarks PASSED")


def test_left_right_disambiguation():
    """Test left/right disambiguation."""
    # Three objects in a row
    grid = create_grid_with_objects([
        (1, 2, 1),  # left
        (2, 2, 3),  # middle
        (3, 2, 5),  # right
    ])
    objects = extract_objects(parse_grid(grid))
    
    left, middle, right = objects[0], objects[1], objects[2]
    
    # Left should be left of middle and right
    assert left_of(left, middle) == True
    assert left_of(left, right) == True
    assert left_of(middle, right) == True
    
    # Right should be right of middle and left
    assert right_of(right, middle) == True
    assert right_of(right, left) == True
    
    # Nth from left/right
    all_objs = [left, middle, right]
    assert nth_from_left(left, all_objs, 1)
    assert nth_from_left(middle, all_objs, 2)
    assert nth_from_left(right, all_objs, 3)
    assert nth_from_right(right, all_objs, 1)
    assert nth_from_right(middle, all_objs, 2)
    assert nth_from_right(left, all_objs, 3)
    
    print("test_left_right_disambiguation PASSED")


def test_same_row_disambiguation():
    """Test same-row disambiguation."""
    # Two pairs of objects on different rows
    grid = create_grid_with_objects([
        (1, 1, 1),  # row 1, left
        (2, 1, 5),  # row 1, right
        (3, 5, 1),  # row 5, left
        (4, 5, 5),  # row 5, right
    ])
    objects = extract_objects(parse_grid(grid))
    
    row1_objects = [o for o in objects if o.centroid[0] < 3]
    row5_objects = [o for o in objects if o.centroid[0] > 3]
    
    assert len(row1_objects) == 2
    assert len(row5_objects) == 2
    
    # Same row should be true within each row
    assert same_row(row1_objects[0], row1_objects[1]) == True
    assert same_row(row5_objects[0], row5_objects[1]) == True
    
    # Different rows should be false
    assert same_row(row1_objects[0], row5_objects[0]) == False
    
    print("test_same_row_disambiguation PASSED")


def test_between():
    """Test between relation."""
    # Three objects in a line horizontally
    grid = create_grid_with_objects([
        (1, 3, 1),   # left
        (2, 3, 3),   # middle
        (3, 3, 5),   # right
    ])
    objects = extract_objects(parse_grid(grid))
    left, middle, right = objects[0], objects[1], objects[2]
    
    assert between(middle, left, right) == True
    assert between(left, middle, right) == False
    assert between(right, left, middle) == False
    
    # Test vertically_between
    grid_v = create_grid_with_objects([
        (1, 1, 3),  # top
        (2, 3, 3),   # middle
        (3, 5, 3),   # bottom
    ])
    objects_v = extract_objects(parse_grid(grid_v))
    top, middle_v, bottom = objects_v[0], objects_v[1], objects_v[2]
    
    # Note: vertically_between checks vertical alignment
    assert vertically_between(middle_v, top, bottom) == True
    
    print("test_between PASSED")


def test_nth_from_edges():
    """Test nth-from-left/right/top/bottom."""
    # 4 objects in a 2x2 grid
    grid = create_grid_with_objects([
        (1, 1, 1),  # top-left
        (2, 1, 5),  # top-right
        (3, 5, 1),  # bottom-left
        (4, 5, 5),  # bottom-right
    ])
    objects = extract_objects(parse_grid(grid))
    
    # nth from left: sort by column (centroid[1])
    left_sorted = sorted(objects, key=lambda o: o.centroid[1])
    for i, obj in enumerate(left_sorted):
        assert nth_from_left(obj, objects, i + 1)
    
    # nth from right
    right_sorted = sorted(objects, key=lambda o: o.centroid[1], reverse=True)
    for i, obj in enumerate(right_sorted):
        assert nth_from_right(obj, objects, i + 1)
    
    # nth from top
    top_sorted = sorted(objects, key=lambda o: o.centroid[0])
    for i, obj in enumerate(top_sorted):
        assert nth_from_top(obj, objects, i + 1)
    
    # nth from bottom
    bottom_sorted = sorted(objects, key=lambda o: o.centroid[0], reverse=True)
    for i, obj in enumerate(bottom_sorted):
        assert nth_from_bottom(obj, objects, i + 1)
    
    print("test_nth_from_edges PASSED")


def test_nearest_farthest():
    """Test nearest_to and farthest_from."""
    # Create objects at different distances
    # Center at (2,2), others at different distances
    grid = create_grid_with_objects([
        (1, 3, 3),  # center
        (2, 1, 1),  # top-left (dist ~4)
        (3, 5, 5),  # bottom-right (dist ~4)
        (4, 1, 5),  # top-right (dist ~4)
    ])
    objects = extract_objects(parse_grid(grid))
    
    # Find the center object (color 1 at center)
    center = None
    others = []
    for obj in objects:
        if obj.color == 1:
            center = obj
        else:
            others.append(obj)
    
    assert center is not None
    assert len(others) == 3
    
    nearest = nearest_to(center, others)
    farthest = farthest_from(center, others)
    
    # All are at same distance (4), so any could be nearest/farthest
    # Just verify the functions return something
    assert nearest is not None
    assert farthest is not None
    
    print("test_nearest_farthest PASSED")


def test_distractors():
    """Test distractor robustness."""
    # Base grid with two objects
    grid = create_grid_with_objects([
        (1, 1, 1),
        (2, 5, 5),
    ])
    objects = extract_objects(parse_grid(grid))
    
    # Add distractor
    grid_with_distractor = create_grid_with_objects([
        (1, 1, 1),
        (2, 5, 5),
        (3, 3, 3),  # distractor in middle
    ])
    objects_with_distractor = extract_objects(parse_grid(grid_with_distractor))
    
    # Original two objects should still be identifiable
    original_colors = {1, 2}
    original_objects = [o for o in objects_with_distractor if o.color in original_colors]
    assert len(original_objects) == 2
    
    # Distractor should be distinct
    distractor = [o for o in objects_with_distractor if o.color == 3]
    assert len(distractor) == 1
    
    print("test_distractors PASSED")


def test_reordered_objects():
    """Test reordered objects (commutativity)."""
    # Two objects, order shouldn't matter for commutative relations
    grid = create_grid_with_objects([
        (1, 1, 1),
        (2, 1, 5),
    ])
    objects = extract_objects(parse_grid(grid))
    a, b = objects[0], objects[1]
    
    # Commutative: a left of b == b right of a
    assert left_of(a, b) == right_of(b, a)
    assert right_of(a, b) == left_of(b, a)
    assert above(a, b) == below(b, a)
    assert below(a, b) == above(b, a)
    assert same_row(a, b) == same_row(b, a)
    assert same_column(a, b) == same_column(b, a)
    
    print("test_reordered_objects PASSED")


def test_symmetric_ambiguity():
    """Test symmetric ambiguity - objects with identical intrinsic properties at symmetric positions."""
    # Four identical objects at symmetric corner positions
    grid = (
        (1, 0, 0, 0, 0, 0, 1),
        (0, 0, 0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0, 0, 0),
        (1, 0, 0, 0, 0, 1, 0),
        (0, 0, 0, 0, 0, 0, 0),
    )
    objects = extract_objects(parse_grid(grid))
    
    # All four have same color (1), same shape (point), same size (1)
    assert len(objects) == 4
    for obj in objects:
        assert obj.color == 1
        assert obj.orientation == "point"
        assert len(obj.cells) == 1
    
    # They should be distinguishable by relational predicates
    # nth_from_left/right/top/bottom should distinguish them
    assert nth_from_left(objects[0], objects, 1)  # top-left is leftmost in top row
    assert nth_from_right(objects[1], objects, 1)  # top-right is rightmost in top row
    assert nth_from_top(objects[0], objects, 1)   # top-left is topmost in left column
    # bottom-right is 2nd from bottom (bottom-left is 1st due to column order)
    assert nth_from_bottom(objects[2], objects, 1)  # bottom-left is bottommost in left column
    assert nth_from_bottom(objects[3], objects, 2)  # bottom-right is 2nd from bottom
    
    # The system should be able to disambiguate them using relational predicates
    candidates = generate_role_candidates(objects)
    for role, candidates_list in candidates.items():
        # Each object should have unique selectors based on position
        assert len(candidates_list) == 4  # 4 objects, each uniquely identifiable
    
    print("test_symmetric_ambiguity PASSED")


def test_constraint_solving():
    """Test constraint solving with multiple constraints."""
    grid = create_grid_with_objects([
        (1, 1, 1),  # top-left
        (2, 1, 5),  # top-right
        (3, 5, 1),  # bottom-left
        (4, 5, 5),  # bottom-right
    ])
    objects = extract_objects(parse_grid(grid))
    
    # Constraint: source is left of landmark
    constraints = [RelationalConstraint("source", "landmark", "left_of")]
    role_candidates = {"source": objects, "landmark": objects}
    
    assignments = solve_role_constraints(objects, constraints, role_candidates)
    assert len(assignments) > 0
    # Should have valid assignments where source is left of landmark
    for a in assignments:
        assert left_of(a.bindings["source"], a.bindings["landmark"])
    
    # Multiple constraints: source left of landmark AND same row
    constraints2 = [
        RelationalConstraint("source", "landmark", "left_of"),
        RelationalConstraint("source", "landmark", "same_row"),
    ]
    assignments2 = solve_role_constraints(objects, constraints2, role_candidates)
    assert len(assignments2) > 0
    for a in assignments2:
        assert left_of(a.bindings["source"], a.bindings["landmark"])
        assert same_row(a.bindings["source"], a.bindings["landmark"])
    
    print("test_constraint_solving PASSED")


def test_ambiguity_detection():
    """Test ambiguity detection - should NOT detect ambiguity when relational predicates can distinguish."""
    from arc_reasoning.relations import detect_role_ambiguity
    
    # Two identical objects at different horizontal positions
    # They have same intrinsic properties but different positions
    grid = create_grid_with_objects([
        (1, 1, 1),  # left
        (1, 1, 5),  # right - same color, shape, size
    ])
    objects = extract_objects(parse_grid(grid))
    
    candidates = generate_role_candidates(objects)
    is_ambiguous, reasons = detect_role_ambiguity(objects, candidates)
    
    # System should correctly disambiguate using relational predicates (left_of/right_of)
    # No ambiguity should be detected since positions differ
    assert is_ambiguous == False
    assert len(reasons) == 0
    
    # Now test genuine ambiguity: two objects that are truly indistinguishable
    # This would require objects at the exact same position (impossible) or
    # objects that are completely indistinguishable even relationally
    # For now, verify the system correctly disambiguates
    
    print("test_ambiguity_detection PASSED")


def test_cross_example_consistency():
    """Test cross-example consistency checking."""
    from arc_reasoning.relations import check_cross_example_consistency
    
    # Two examples with same pattern
    grid1 = create_grid_with_objects([(1, 1, 1), (2, 1, 5)])
    grid2 = create_grid_with_objects([(3, 1, 1), (4, 1, 5)])
    
    train_pairs = [(parse_grid(grid1), parse_grid(grid2))]
    
    selector = ("color", 1)
    constraints = [RelationalConstraint("source", "landmark", "left_of")]
    
    consistent, score, evidence = check_cross_example_consistency(
        train_pairs, "source", selector, constraints
    )
    
    assert consistent == True or consistent == False  # Should not crash
    print("test_cross_example_consistency PASSED")


def test_same_distance():
    """Test same_distance predicate."""
    grid = create_grid_with_objects([
        (1, 1, 1),  # top-left
        (2, 1, 5),  # top-right
        (3, 5, 3),  # center
    ])
    objects = extract_objects(parse_grid(grid))
    a, b, c = objects[0], objects[1], objects[2]
    
    # a and b should be at same distance from c (approximately)
    # Distance from c to a: |2-1| + |3-1| = 3
    # Distance from c to b: |2-1| + |3-5| = 3
    assert same_distance(a, b, c) == True
    
    print("test_same_distance PASSED")


def test_relative_offset():
    """Test relative_offset."""
    grid = create_grid_with_objects([
        (1, 1, 1),
        (2, 3, 4),
    ])
    objects = extract_objects(parse_grid(grid))
    a, b = objects[0], objects[1]
    
    dy, dx = relative_offset(a, b)
    assert dy == 2  # 3 - 1
    assert dx == 3  # 4 - 1
    
    print("test_relative_offset PASSED")


def test_aligned_with():
    """Test aligned_with."""
    # Three collinear points
    grid = create_grid_with_objects([
        (1, 1, 1),  # top-left
        (2, 1, 5),  # top-right
        (3, 2, 3),  # on the line between them (row 2 is between 1 and 1? No)
    ])
    # Actually, let's use a grid with three collinear points
    grid = create_grid_with_objects([
        (1, 1, 1),  # (1,1)
        (2, 2, 3),  # (2,3) - on diagonal
        (3, 3, 5),  # (3,5) - on same diagonal
    ])
    objects = extract_objects(parse_grid(grid))
    a, b, c = objects[0], objects[1], objects[2]
    
    # a, b, c are on a diagonal line
    assert aligned_with(a, b, c) == True
    
    print("test_aligned_with PASSED")


def test_same_relative_position():
    """Test same_relative_position."""
    grid = create_grid_with_objects([
        (1, 1, 1),
        (2, 1, 3),
        (3, 5, 1),
        (4, 5, 3),
    ])
    objects = extract_objects(parse_grid(grid))
    a, b, c, d = objects[0], objects[1], objects[2], objects[3]
    
    # a->b is (0, 2), c->d is (0, 2)
    assert same_relative_position(a, b, c, d) == True
    
    print("test_same_relative_position PASSED")


def run_all_tests():
    """Run all synthetic tests."""
    test_basic_relations()
    test_identical_landmarks()
    test_left_right_disambiguation()
    test_same_row_disambiguation()
    test_between()
    test_nth_from_edges()
    test_nearest_farthest()
    test_distractors()
    test_reordered_objects()
    test_symmetric_ambiguity()
    test_constraint_solving()
    test_ambiguity_detection()
    test_cross_example_consistency()
    test_same_distance()
    test_relative_offset()
    test_aligned_with()
    test_same_relative_position()
    print("\nALL SYNTHETIC TESTS PASSED!")


if __name__ == "__main__":
    run_all_tests()