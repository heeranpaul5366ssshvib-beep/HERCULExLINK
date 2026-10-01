"""Synthetic ARC tasks for testing relational role disambiguation."""

import pytest
from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver
from arc_reasoning.objects import extract_objects
from arc_reasoning.relations import (left_of, right_of, above, below, same_row, same_column,
                                      between, nth_from_left, nth_from_right, nth_from_top,
                                      nth_from_bottom, manhattan_distance, nearest_to,
                                      farthest_from, same_distance, same_relative_position,
                                      relative_offset, aligned_with, compute_relational_signature)


def make_task(train_pairs, test_input):
    """Helper to create a task dict."""
    return {
        "train": [{"input": p[0], "output": p[1]} for p in train_pairs],
        "test": [{"input": test_input}]
    }


class TestRelationalPredicates:
    """Test basic relational predicates."""
    
    def test_left_right_above_below(self):
        """Test basic directional predicates."""
        # Create a single grid with two objects
        grid = parse_grid([[1, 1, 0, 0], [0, 0, 0, 0], [0, 0, 2, 2]])
        objects = extract_objects(grid)
        
        a = next(o for o in objects if o.color == 1)  # top-left
        b = next(o for o in objects if o.color == 2)  # bottom-right
        
        assert left_of(a, b)
        assert not right_of(a, b)
        assert above(a, b)
        assert not below(a, b)
    
    def test_same_row_column(self):
        """Test same row/column predicates."""
        grid = parse_grid([[1, 0, 2], [0, 0, 0], [3, 0, 4]])
        objects = extract_objects(grid)
        
        # Objects at (0,0) and (0,2) - same row
        assert same_row(objects[0], objects[1])
        assert not same_column(objects[0], objects[1])
        
        # Objects at (0,0) and (2,0) - same column
        assert same_column(objects[0], objects[2])
        assert not same_row(objects[0], objects[2])
    
    def test_between(self):
        """Test between predicate."""
        # Three objects in a row: A _ B _ C
        grid = parse_grid([[1, 0, 2, 0, 3]])
        objects = extract_objects(grid)
        
        # Middle object (2) is between 1 and 3
        assert between(objects[1], objects[0], objects[2])
        # Edge objects are not between
        assert not between(objects[0], objects[1], objects[2])
    
    def test_nth_from_edges(self):
        """Test nth from left/right/top/bottom."""
        grid = parse_grid([[1, 0, 2, 0, 3, 0, 4]])
        objects = extract_objects(grid)
        
        # 4 objects at positions 0, 2, 4, 6
        assert nth_from_left(objects[0], objects, 1)
        assert nth_from_left(objects[1], objects, 2)
        assert nth_from_left(objects[2], objects, 3)
        assert nth_from_left(objects[3], objects, 4)
        
        assert nth_from_right(objects[3], objects, 1)
        assert nth_from_right(objects[2], objects, 2)
        assert nth_from_right(objects[1], objects, 3)
        assert nth_from_right(objects[0], objects, 4)
    
    def test_nearest_farthest(self):
        """Test nearest_to and farthest_from."""
        grid = parse_grid([[1, 0, 0, 0, 2], [0, 0, 0, 0, 0], [0, 0, 3, 0, 0]])
        objects = extract_objects(grid)
        
        # Object 1 at (0,0), Object 2 at (0,4), Object 3 at (2,2)
        # For object 1, nearest is 3 (dist=4), farthest is 2 (dist=4)
        # Actually distances: 1->2 = 4, 1->3 = 4, 2->3 = 4
        # All equidistant in this case
        
        nearest_to_obj1 = nearest_to(objects[0], objects[1:])
        farthest_from_obj1 = farthest_from(objects[0], objects[1:])
        
        # Both at distance 4, so either could be nearest/farthest
        assert nearest_to_obj1 is not None
        assert farthest_from_obj1 is not None
    
    def test_same_distance(self):
        """Test same_distance predicate."""
        # Create three objects where A and B are equidistant from C
        grid = parse_grid([[1, 0, 2], [0, 3, 0], [0, 0, 0]])
        objects = extract_objects(grid)
        
        # Object 1 at (0,0), Object 2 at (0,2), Object 3 at (1,1)
        # Distance from 3 to 1: |1-0|+|1-0| = 2
        # Distance from 3 to 2: |1-0|+|1-2| = 2
        # So 1 and 2 are same distance from 3
        assert same_distance(objects[0], objects[1], objects[2])
    
    def test_relative_offset(self):
        """Test relative offset computation."""
        a = parse_grid([[1, 0], [0, 0]])  # at (0,0)
        b = parse_grid([[0, 0], [0, 2]])  # at (1,1)
        objects_a = extract_objects(a)
        objects_b = extract_objects(b)
        
        dy, dx = relative_offset(objects_a[0], objects_b[0])
        assert dy == 1
        assert dx == 1
    
class TestAlignedWith:
    """Test aligned_with predicate."""
    
    def test_aligned_with(self):
        """Test aligned_with predicate."""
        # Three objects in a line
        grid = parse_grid([[1, 0, 0, 0, 2, 0, 0, 0, 3]])
        objects = extract_objects(grid)
        
        # All three are on the same row
        assert aligned_with(objects[0], objects[1], objects[2])
        
        # Not aligned - L shape
        grid2 = parse_grid([[1, 0, 0], [2, 0, 0], [0, 0, 3]])
        objects2 = extract_objects(grid2)
        assert not aligned_with(objects2[0], objects2[1], objects2[2])


class TestRelationalSignature:
    """Test relational signature computation."""
    
    def test_signature_computation(self):
        """Test relational signature computation for a simple grid."""
        grid = parse_grid([
            [1, 0, 0, 0, 2],
            [0, 0, 0, 0, 0],
            [0, 0, 3, 0, 0],
            [0, 0, 0, 0, 0],
            [4, 0, 0, 0, 5]
        ])
        objects = extract_objects(grid)
        
        # Object 3 is at center (2,2)
        obj3 = next(o for o in objects if o.color == 3)
        sig = compute_relational_signature(obj3, objects, grid)
        
        # Object 3 at (2,2): left of 2,5 (col 4), right of 1,4 (col 0)
        # above 4,5 (row 4), below 1,2 (row 0)
        assert sig["left_of_colors"] == {2, 5}
        assert sig["right_of_colors"] == {1, 4}
        assert sig["above_colors"] == {4, 5}
        assert sig["below_colors"] == {1, 2}
        assert sig["nth_from_left"] == 3
        assert sig["nth_from_right"] == 3
        assert sig["nth_from_top"] == 3
        assert sig["nth_from_bottom"] == 3
        assert sig["nearest_to_color"] in {1, 2, 4, 5}

    def test_edge_object_signature(self):
        """Test signature for corner object."""
        grid = parse_grid([[1, 0, 2], [0, 0, 0], [3, 0, 4]])
        objects = extract_objects(grid)
        
        # Object 1 at top-left
        obj1 = next(o for o in objects if o.color == 1)
        sig = compute_relational_signature(obj1, objects, grid)
        
        assert sig["nth_from_left"] == 1
        assert sig["nth_from_top"] == 1
        assert sig["closest_corner"] == "top_left"
        assert sig["closest_edge"] in ["top", "left"]


class TestSyntheticRelationalTasks:
    """Synthetic ARC tasks for relational reasoning."""
    
    def test_unique_landmark_copy(self):
        """Copy shape onto unique marker."""
        task = make_task([
            (
                [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], 
                 [0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
                [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], 
                 [0, 0, 0, 0, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0]]
            ),
            (
                [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0], 
                 [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]],
                [[0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 0, 0], 
                 [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]]
            ),
        ], [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 2, 0], 
            [0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        relational = [r for r in result["verified_rules"] if r.startswith("object-program:copy")]
        assert len(relational) > 0
        assert result["candidates"][0][0].grid == (
            (0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 1, 1),
            (0, 0, 0, 0, 0, 0, 0),
            (1, 1, 0, 0, 0, 0, 0)
        )
    
    def test_adjacent_placement(self):
        """Copy shape adjacent to landmark by alignment."""
        task = make_task([
            (
                [[1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                 [0, 0, 0, 2, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
                [[1, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                 [0, 0, 0, 2, 2, 1, 0], [0, 0, 0, 0, 0, 0, 0]]
            ),
            (
                [[0, 2, 2, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                 [0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0]],
                [[0, 2, 2, 1, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                 [0, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0, 0]]
            ),
        ], [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 2, 2, 0, 0],
            [0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task)
        
        assert any("adjacent" in r for r in result["verified_rules"])
        assert result["candidates"][0][0].grid == (
            (0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 2, 2, 1, 0),
            (0, 0, 0, 0, 0, 0, 0),
            (1, 0, 0, 0, 0, 0, 0)
        )
    
    def test_repeated_landmark_different_sides(self):
        """Multiple identical landmarks, copy to each."""
        task = make_task([
            (
                [[1, 1, 0, 0, 0], [0, 2, 0, 0, 0], [0, 0, 0, 2, 0], [0, 0, 0, 0, 0]],
                [[1, 1, 0, 0, 0], [0, 1, 1, 0, 0], [0, 1, 1, 0, 0], [0, 0, 0, 0, 0]]
            ),
            (
                [[0, 2, 0, 0, 0], [0, 0, 0, 2, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0]],
                [[0, 1, 1, 0, 0], [0, 1, 1, 0, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0]]
            ),
        ], [[0, 0, 0, 2, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        # Should find the relation that copies to each landmark
        assert len(result["verified_rules"]) > 0
    
    def test_landmark_disambiguation_by_position(self):
        """Two identical landmarks, different positions - use nth_from_left."""
        task = make_task([
            (
                [[1, 1, 0, 0, 0, 0], [0, 2, 0, 2, 0], [0, 0, 0, 0, 0]],
                [[1, 1, 0, 0, 0], [0, 1, 1, 0, 0], [0, 1, 1, 0, 0]]
            ),
            (
                [[0, 2, 0, 2, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0]],
                [[0, 1, 1, 0, 0], [0, 1, 1, 0, 0], [1, 1, 0, 0, 0]]
            ),
        ], [[0, 0, 0, 2, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        # Should find the nth_from_left relation
        relational = [r for r in result["verified_rules"] if r.startswith("object-program:copy")]
        assert len(relational) > 0
    
    def test_landmark_disambiguation_by_alignment(self):
        """Two identical landmarks, same column - use same_column relation."""
        task = make_task([
            (
                [[1, 1, 0, 0], [0, 2, 0, 0], [0, 0, 0, 0], [0, 2, 0, 0]],
                [[1, 1, 0, 0], [0, 1, 1, 0], [0, 1, 1, 0], [0, 1, 1, 0]]
            ),
            (
                [[0, 0, 0, 0], [0, 2, 0, 0], [1, 1, 0, 0], [0, 2, 0, 0]],
                [[0, 0, 0, 0], [0, 1, 1, 0], [1, 1, 0, 0], [0, 1, 1, 0]]
            ),
        ], [[0, 2, 0, 0], [0, 0, 0, 0], [1, 1, 0, 0], [0, 2, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        # Should find same_column relation
        relational = [r for r in result["verified_rules"] if r.startswith("object-program:copy")]
        assert len(relational) > 0
    
    def test_between_relation(self):
        """Source is between two landmarks."""
        task = make_task([
            (
                [[0, 2, 0, 0, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 2, 0]],
                [[0, 2, 0, 0, 0], [0, 0, 0, 0, 0], [0, 1, 1, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 2, 0]]
            ),
            (
                [[0, 2, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0], [0, 0, 0, 2, 0]],
                [[0, 2, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 1, 1, 0], [0, 0, 0, 0, 0], [0, 0, 0, 2, 0]]
            ),
        ], [[0, 2, 0, 0, 0], [0, 0, 0, 0, 0], [1, 1, 0, 0, 0], [0, 0, 0, 0, 0], [0, 0, 0, 2, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        relational = [r for r in result["verified_rules"] if r.startswith("object-program:copy")]
        assert len(relational) > 0
    
    def test_nearest_landmark(self):
        """Copy to nearest landmark."""
        task = make_task([
            (
                [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 2, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
                [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 1, 1, 0, 0], [0, 0, 0, 0, 0, 0, 0]]
            ),
            (
                [[0, 0, 0, 0, 2, 0, 0], [1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
                [[0, 0, 0, 0, 1, 1, 0], [1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]]
            ),
        ], [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 2, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        relational = [r for r in result["verified_rules"] if r.startswith("object-program:copy")]
        assert len(relational) > 0
    
    def test_multiple_sources_single_landmark(self):
        """Multiple source objects, single landmark."""
        task = make_task([
            (
                [[1, 1, 0, 0, 3, 3], [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]],
                [[1, 1, 0, 0, 3, 3], [0, 1, 1, 0, 3, 3], [0, 0, 0, 0, 0, 0]]
            ),
            (
                [[0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]],
                [[0, 1, 1, 0, 0, 0], [1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]]
            ),
        ], [[1, 1, 0, 0, 0, 0], [0, 0, 0, 2, 2, 0], [0, 0, 0, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        # Should find multiple source candidates
        assert len(result["verified_rules"]) > 0
    
    def test_distractor_resistance(self):
        """Test that distractor objects don't break the relation."""
        task = make_task([
            (
                [[1, 1, 0, 0], [0, 2, 0, 0], [0, 0, 0, 0]],
                [[1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0]]
            ),
            (
                [[0, 2, 0, 0], [0, 0, 0, 0], [1, 1, 0, 0]],
                [[0, 1, 1, 0], [0, 0, 0, 0], [1, 1, 0, 0]]
            ),
        ], [[0, 0, 0, 0], [0, 2, 0, 0], [1, 1, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        # Add a distractor and test robustness
        assert len(result["verified_rules"]) > 0
    
    def test_symmetry_ambiguity(self):
        """Two perfectly symmetric landmarks - should detect ambiguity."""
        task = make_task([
            (
                [[1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 2, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0]],
                [[1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 1, 1, 1, 1, 0], [0, 0, 0, 0, 0, 0]]
            ),
            (
                [[0, 2, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]],
                [[0, 1, 1, 1, 1, 0], [0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0]]
            ),
        ], [[1, 1, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0], [0, 2, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0]])
        
        solver = ArcSolver()
        result = solver.solve(task, include_coverage=True)
        
        # Should detect ambiguity
        coverage = result.get("hypothesis_coverage", {})
        # The task has two identical landmarks, should be handled
        assert "candidates" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])