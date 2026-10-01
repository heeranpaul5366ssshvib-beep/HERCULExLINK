"""Role-based object relations and relation-conditioned copy placement."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations, permutations
from typing import Iterable

from .deltas import compare_grids
from .grid import Grid, infer_background
from .objects import (ArcObject, extract_objects, normalized_shape,
                      left_of, right_of, above, below, same_row, same_column,
                      between, vertically_between, nth_from_left, nth_from_right,
                      nth_from_top, nth_from_bottom, manhattan_distance,
                      nearest_to, farthest_from, same_distance, same_relative_position,
                      relative_offset, aligned_with, compute_relational_signature)
from .rules import Rule


Selector = tuple

# ============================================================
# RELATIONAL PREDICATE FUNCTIONS (re-exported from objects)
# ============================================================

# These are now imported from objects module
# left_of, right_of, above, below, same_row, same_column
# between, vertically_between, nth_from_left, nth_from_right
# nth_from_top, nth_from_bottom, manhattan_distance, chebyshev_distance
# euclidean_distance, nearest_to, farthest_from, same_distance
# closest_to_corner, closest_to_edge, same_relative_position
# relative_offset, aligned_with, compute_relational_signature

# ============================================================
# RELATION GRAPH STRUCTURES
# ============================================================

@dataclass(frozen=True)
class RelationEdge:
    """Explicit relation between two objects with quantitative attributes."""
    source_id: int
    target_id: int
    predicate: str
    attributes: dict = field(default_factory=dict)  # e.g., {"offset": (dy, dx), "distance": 3.5}


@dataclass(frozen=True)
class RelationGraph:
    """Explicit graph of objects and their relations."""
    objects: tuple[ArcObject, ...]
    edges: tuple[RelationEdge, ...]
    # Index for fast lookup
    _edges_by_source: dict[int, list[RelationEdge]] = field(default_factory=dict, init=False)
    _edges_by_target: dict[int, list[RelationEdge]] = field(default_factory=dict, init=False)
    _edges_by_predicate: dict[str, list[RelationEdge]] = field(default_factory=dict, init=False)
    
    def __post_init__(self):
        # Build indices
        for edge in self.edges:
            self._edges_by_source.setdefault(edge.source_id, []).append(edge)
            self._edges_by_target.setdefault(edge.target_id, []).append(edge)
            self._edges_by_predicate.setdefault(edge.predicate, []).append(edge)
    
    def outgoing(self, obj_id: int) -> list[RelationEdge]:
        return self._edges_by_source.get(obj_id, [])
    
    def incoming(self, obj_id: int) -> list[RelationEdge]:
        return self._edges_by_target.get(obj_id, [])
    
    def by_predicate(self, predicate: str) -> list[RelationEdge]:
        return self._edges_by_predicate.get(predicate, [])


# ============================================================
# ROLE DISAMBIGUATION STRUCTURES
# ============================================================

@dataclass(frozen=True)
class RoleBinding:
    """Explicit role assignment for an object."""
    object_id: int
    role: str  # "source", "landmark", "landmark_b", "anchor", "target", etc.
    selector: Selector  # The selector that uniquely identifies this object
    confidence: float  # Based on selector uniqueness, relational evidence


@dataclass(frozen=True)
class CandidateProgram:
    """A complete candidate with role bindings and transformation."""
    role_bindings: tuple[RoleBinding, ...]
    transformation_family: str  # "copy_onto_marker", "align_bbox", "between", etc.
    placement_params: tuple  # Specific placement parameters
    color_policy: str  # "source" or "landmark"
    transformation_fn: callable  # The actual transformation function
    # Evidence across training examples
    training_evidence: dict[int, bool] = field(default_factory=dict)  # example_idx -> pass/fail
    invariance_evidence: dict[str, bool] = field(default_factory=dict)  # perturbation -> pass/fail
    # Scoring components
    parsimony_score: int = 0
    relational_evidence_score: float = 0.0
    cross_example_consistency: float = 0.0
    invariance_score: int = 0


def build_relation_graph(objects: list[ArcObject]) -> RelationGraph:
    """Build explicit relation graph from objects."""
    edges = []
    for i, obj_a in enumerate(objects):
        for j, obj_b in enumerate(objects):
            if i == j:
                continue
            relations = object_relations(obj_a, obj_b)
            for rel in relations:
                attrs = {}
                if rel in ("offset_by", "offset_by_vector"):
                    dy = obj_b.centroid[0] - obj_a.centroid[0]
                    dx = obj_b.centroid[1] - obj_a.centroid[1]
                    attrs["offset"] = (dy, dx)
                elif rel in ("nearest", "farthest"):
                    dy = obj_b.centroid[0] - obj_a.centroid[0]
                    dx = obj_b.centroid[1] - obj_a.centroid[1]
                    attrs["distance"] = (dy * dy + dx * dx) ** 0.5
                elif rel in ("aligned_x", "aligned_y", "same_row", "same_column"):
                    attrs["axis"] = "x" if rel in ("aligned_x", "same_column") else "y"
                edges.append(RelationEdge(i, j, rel, attrs))
    return RelationGraph(tuple(objects), tuple(edges))


# Phase 3: ROLE DISAMBIGUATION - Generate candidate bindings
def generate_role_candidates(objects: list[ArcObject], 
                             source_color: int | None = None,
                             landmark_color: int | None = None) -> dict[str, list[RoleBinding]]:
    """
    For each potential role, generate ALL candidate objects that could fill it.
    Returns dict of role -> list of candidate RoleBindings.
    """
    candidates = defaultdict(list)
    
    for obj_id, obj in enumerate(objects):
        # Generate all selectors that uniquely identify this object
        selectors = _selector_specs(objects, obj)
        for selector in selectors:
            # Determine potential roles based on object properties and selector type
            kind = selector[0]
            
            # Source candidates: objects that could be copied
            if source_color is None or obj.color == source_color:
                candidates["source"].append(RoleBinding(
                    object_id=obj_id,
                    role="source",
                    selector=selector,
                    confidence=_compute_role_confidence(obj, "source", objects, selector)
                ))
            
            # Landmark candidates: objects that could serve as reference
            if landmark_color is None or obj.color == landmark_color:
                candidates["landmark"].append(RoleBinding(
                    object_id=obj_id,
                    role="landmark",
                    selector=selector,
                    confidence=_compute_role_confidence(obj, "landmark", objects, selector)
                ))
            
            # Anchor candidates: unique, stable reference points
            if kind in ("unique-color", "unique-shape", "unique-size", "point", "largest", "smallest"):
                candidates["anchor"].append(RoleBinding(
                    object_id=obj_id,
                    role="anchor",
                    selector=selector,
                    confidence=_compute_role_confidence(obj, "anchor", objects, selector)
                ))
            
            # Marker candidates: small, distinct objects
            if kind in ("point", "unique-color", "unique-shape", "unique-size"):
                candidates["marker"].append(RoleBinding(
                    object_id=obj_id,
                    role="marker",
                    selector=selector,
                    confidence=_compute_role_confidence(obj, "marker", objects, selector)
                ))
    
    return dict(candidates)


def _compute_role_confidence(obj: ArcObject, role: str, 
                            all_objects: list[ArcObject], selector: Selector) -> float:
    """Compute confidence score for a role assignment."""
    base_confidence = 1.0
    kind = selector[0]
    
    # Unique selectors are more confident
    if kind in ("unique-color", "unique-shape", "unique-size", "unique-color", "unique-size"):
        base_confidence += 0.5
    elif kind in ("largest", "smallest"):
        base_confidence += 0.3
    elif kind == "point":
        base_confidence += 0.2
    
    # Role-specific bonuses
    if role == "source":
        # Prefer objects with distinct shape (more likely to be copied)
        shape_counts = Counter(normalized_shape(o) for o in all_objects)
        if shape_counts[normalized_shape(obj)] == 1:
            base_confidence += 0.2
    elif role == "landmark":
        # Prefer stable, distinctive landmarks
        if kind in ("unique-color", "unique-shape", "unique-size", "largest", "smallest"):
            base_confidence += 0.3
        # Prefer objects with high connectivity to others (central in relation graph)
        if len(obj.adjacent_colors) > 0:
            base_confidence += 0.2
    elif role == "anchor":
        # Prefer unique, stable anchors
        if kind in ("unique-color", "unique-shape", "unique-size"):
            base_confidence += 0.5
    
    # Penalty for objects that are enclosed (less likely to be independent landmarks)
    if len(obj.enclosed_by) > 0:
        base_confidence -= 0.2
    
    return min(base_confidence, 1.0)


# Cross-example role validation
def validate_role_bindings_across_examples(
    train_pairs: list[tuple[Grid, Grid]],
    candidate_program: CandidateProgram
) -> tuple[bool, dict]:
    """
    Test a candidate role binding across ALL training examples.
    Returns (is_valid, evidence_dict).
    """
    evidence = {}
    all_pass = True
    
    for ex_idx, (source, target) in enumerate(train_pairs):
        try:
            # Try to resolve all role bindings in this example
            source_objects = extract_objects(source, background_color=infer_background(source))
            target_objects = extract_objects(target, background_color=infer_background(target))
            
            # Try to find objects matching each role's selector
            bound_objects = {}
            for binding in candidate_program.role_bindings:
                matches = _matches(source_objects, binding.selector)
                if len(matches) != 1:
                    evidence[ex_idx] = False
                    all_pass = False
                    break
                bound_objects[binding.role] = matches[0]
            
            if not all_pass:
                break
            
            # Apply transformation and verify
            result = candidate_program.transformation_fn(source, bound_objects)
            if result != target:
                evidence[ex_idx] = False
                all_pass = False
            else:
                evidence[ex_idx] = True
        except Exception as e:
            evidence[ex_idx] = False
            all_pass = False
    
    return all_pass, evidence


# Distractor robustness testing
def test_distractor_robustness(
    source: Grid,
    candidate_program: CandidateProgram,
    num_distractors: int = 2
) -> bool:
    """
    Test if candidate survives insertion of irrelevant distractor objects.
    """
    from .primitives import fill_enclosed_background
    from .objects import extract_objects
    
    background = infer_background(source)
    objects = extract_objects(source, background_color=background)
    
    if len(objects) < 2:
        return True  # Not enough objects to test
    
    # Try adding distractor objects of various colors/shapes
    distractor_colors = [c for c in range(1, 10) 
                         if c != background and c not in {o.color for o in objects}][:num_distractors]
    
    for distractor_color in distractor_colors:
        # Create a simple distractor object (single pixel) at random empty location
        h, w = len(source), len(source[0])
        for r in range(h):
            for c in range(w):
                if source[r][c] == background:
                    # Try placing distractor here
                    test_grid = [list(row) for row in source]
                    test_grid[r][c] = distractor_color
                    test_grid = tuple(tuple(row) for row in test_grid)
                    
                    # Try to resolve roles and apply transformation
                    try:
                        test_objects = extract_objects(test_grid, background_color=background)
                        bound_objects = {}
                        for binding in candidate_program.role_bindings:
                            matches = _matches(test_objects, binding.selector)
                            if len(matches) != 1:
                                return False  # Distractor broke the selector
                            bound_objects[binding.role] = matches[0]
                        candidate_program.transformation_fn(test_grid, bound_objects)
                    except Exception:
                        return False
    return True


# ============================================================
# CONSTRAINT-BASED ROLE ASSIGNMENT ENGINE
# ============================================================

@dataclass(frozen=True)
class RelationalConstraint:
    """A single relational constraint between two roles."""
    role_a: str
    role_b: str
    predicate: str  # "left_of", "right_of", "above", "below", "same_row", "same_column", "between", "nearest_to", "farthest_from", "nth_from_left", etc.
    value: int | tuple | None = None  # For nth_from_left: n; for between: (role_a, role_b)
    
    def check(self, objects: list[ArcObject], bindings: dict[str, ArcObject]) -> bool:
        """Check if this constraint is satisfied by the given bindings."""
        if self.role_a not in bindings or self.role_b not in bindings:
            return False
        obj_a = bindings[self.role_a]
        obj_b = bindings[self.role_b]
        
        if self.predicate == "left_of":
            return left_of(obj_a, obj_b)
        elif self.predicate == "right_of":
            return right_of(obj_a, obj_b)
        elif self.predicate == "above":
            return above(obj_a, obj_b)
        elif self.predicate == "below":
            return below(obj_a, obj_b)
        elif self.predicate == "same_row":
            return same_row(obj_a, obj_b)
        elif self.predicate == "same_column":
            return same_column(obj_a, obj_b)
        elif self.predicate == "between":
            return between(obj_a, obj_b, bindings.get("landmark_b"))
        elif self.predicate == "vertically_between":
            return vertically_between(obj_a, obj_b, bindings.get("landmark_b"))
        elif self.predicate == "nearest_to":
            return obj_b == nearest_to(obj_a, [o for o in objects if o.cells != obj_a.cells])
        elif self.predicate == "farthest_from":
            return obj_b == farthest_from(obj_a, [o for o in objects if o.cells != obj_a.cells])
        elif self.predicate == "same_distance":
            return same_distance(obj_a, obj_b, bindings.get("landmark_c"))
        elif self.predicate == "same_relative_position":
            return same_relative_position(obj_a, obj_b, bindings.get("landmark_c"), bindings.get("landmark_d"))
        elif self.predicate == "nth_from_left":
            return nth_from_left(obj_a, objects, self.value)
        elif self.predicate == "nth_from_right":
            return nth_from_right(obj_a, objects, self.value)
        elif self.predicate == "nth_from_top":
            return nth_from_top(obj_a, objects, self.value)
        elif self.predicate == "nth_from_bottom":
            return nth_from_bottom(obj_a, objects, self.value)
        elif self.predicate == "aligned_with":
            return aligned_with(obj_a, obj_b, bindings.get("landmark_c"))
        return True


@dataclass(frozen=True)
class RoleAssignment:
    """A complete role assignment with all bindings and constraints."""
    bindings: dict[str, ArcObject]  # role -> object
    constraints: tuple[RelationalConstraint, ...]
    score: float = 0.0
    is_ambiguous: bool = False
    ambiguity_reason: str = ""


def solve_role_constraints(
    objects: list[ArcObject],
    constraints: list[RelationalConstraint],
    role_candidates: dict[str, list[ArcObject]]
) -> list[RoleAssignment]:
    """
    Solve role assignment as a constraint satisfaction problem.
    
    Args:
        objects: All objects in the scene
        constraints: List of relational constraints between roles
        role_candidates: Dict mapping role name to list of candidate objects
        
    Returns:
        List of valid role assignments, sorted by score (best first)
    """
    # Generate all possible assignments
    role_names = list(role_candidates.keys())
    assignments = []
    
    # Generate all combinations of candidates for each role
    def generate_assignments(idx: int, current: dict[str, ArcObject]):
        if idx == len(role_names):
            # Check all constraints
            valid = True
            for constraint in constraints:
                if not constraint.check(objects, current):
                    valid = False
                    break
            if valid:
                # Compute score based on constraint satisfaction and candidate confidence
                score = compute_assignment_score(current, constraints, objects)
                assignments.append(RoleAssignment(
                    bindings=current,
                    constraints=tuple(constraints),
                    score=score
                ))
            return
        
        role = role_names[idx]
        for obj in role_candidates[role]:
            if obj.cells not in [o.cells for o in current.values()]:
                generate_assignments(idx + 1, {**current, role_names[idx]: obj})
    
    generate_assignments(0, {})
    
    # Sort by score descending
    assignments.sort(key=lambda a: a.score, reverse=True)
    
    # Detect ambiguity
    if len(assignments) > 1 and abs(assignments[0].score - assignments[1].score) < 0.1:
        assignments[0] = RoleAssignment(
            bindings=assignments[0].bindings,
            constraints=assignments[0].constraints,
            score=assignments[0].score,
            is_ambiguous=True,
            ambiguity_reason="Multiple high-scoring assignments"
        )
    
    return assignments


def compute_assignment_score(bindings: dict[str, ArcObject], 
                           constraints: list[RelationalConstraint],
                           objects: list[ArcObject]) -> float:
    """Compute a score for a role assignment based on relational evidence."""
    score = 1.0
    
    # Base score from constraint satisfaction (all must pass)
    score = 1.0
    
    # Bonus for each satisfied constraint
    for constraint in constraints:
        # All constraints must be satisfied (checked before calling this)
        score += 0.5
    
    # Bonus for relational signatures matching
    for role, obj in bindings.items():
        if hasattr(obj, 'relative_signature'):
            score += 0.1
    
    # Penalty for objects that are enclosed (less likely to be landmarks)
    for obj in bindings.values():
        if len(obj.enclosed_by) > 0:
            score -= 0.2
    
    return score


def generate_relational_constraints_from_examples(
    train_pairs: list[tuple[Grid, Grid]],
    source_role: str = "source",
    landmark_role: str = "landmark"
) -> list[RelationalConstraint]:
    """
    Infer relational constraints from training examples.
    
    Analyzes training pairs to discover consistent relational patterns
    between the source and landmark objects.
    """
    constraints = []
    
    if len(train_pairs) < 2:
        return constraints
    
    # Extract objects from all training examples
    all_source_objects = []
    all_target_objects = []
    for source, target in train_pairs:
        bg = infer_background(source)
        all_source_objects.append(extract_objects(source, background_color=bg))
        all_target_objects.append(extract_objects(target, background_color=infer_background(target)))
    
    # For each example, find the source and landmark objects
    # (In practice, we'd use the selectors to identify them)
    # For now, we infer constraints from consistent patterns
    
    # Check for consistent left_of/right_of/above/below relations
    predicates = [
        ("left_of", left_of),
        ("right_of", right_of),
        ("above", above),
        ("below", below),
        ("same_row", same_row),
        ("same_column", same_column),
    ]
    
    # Analyze first two examples to find consistent relations
    if len(all_source_objects) >= 2:
        for pred_name, pred_fn in predicates:
            consistent = True
            for ex_idx, (source, target) in enumerate(train_pairs[:2]):
                bg = infer_background(source)
                objects = extract_objects(source, background_color=bg)
                # Find potential source/landmark pairs
                # This is simplified - in practice we'd use the actual selectors
                # For now, skip automatic constraint generation
                pass
    
    return constraints


def discover_consistent_constraints(
    train_pairs: list[tuple[Grid, Grid]],
    candidate_bindings: list[dict[str, ArcObject]]
) -> list[RelationalConstraint]:
    """
    Discover relational constraints that are consistent across all training examples.
    
    Args:
        train_pairs: Training input/output pairs
        candidate_bindings: List of candidate role bindings for each example
        
    Returns:
        List of constraints that hold across ALL examples
    """
    if len(candidate_bindings) < 2:
        return []
    
    # Check each possible relational predicate
    predicates = [
        ("left_of", left_of),
        ("right_of", right_of),
        ("above", above),
        ("below", below),
        ("same_row", same_row),
        ("same_column", same_column),
    ]
    
    consistent_constraints = []
    
    for pred_name, pred_fn in predicates:
        # Check if this relation holds between the same roles in all examples
        all_hold = True
        for bindings in candidate_bindings:
            if "source" not in bindings or "landmark" not in bindings:
                all_hold = False
                break
            if not pred_fn(bindings["source"], bindings["landmark"]):
                all_hold = False
                break
        
        if all_hold:
            consistent_constraints.append(RelationalConstraint(
                role_a="source",
                role_b="landmark",
                predicate=pred_name
            ))
    
    return consistent_constraints


# Cross-example role validation (enhanced)
def validate_role_bindings_across_examples_enhanced(
    train_pairs: list[tuple[Grid, Grid]],
    candidate_program: CandidateProgram,
    constraints: list[RelationalConstraint] | None = None
) -> tuple[bool, dict]:
    """
    Test a candidate role binding across ALL training examples with constraint checking.
    Returns (is_valid, evidence_dict).
    """
    evidence = {}
    all_pass = True
    
    for ex_idx, (source, target) in enumerate(train_pairs):
        try:
            source_objects = extract_objects(source, background_color=infer_background(source))
            target_objects = extract_objects(target, background_color=infer_background(target))
            
            # Try to find objects matching each role's selector
            bound_objects = {}
            for binding in candidate_program.role_bindings:
                matches = _matches(source_objects, binding.selector)
                if len(matches) != 1:
                    evidence[ex_idx] = False
                    all_pass = False
                    break
                bound_objects[binding.role] = matches[0]
            
            if not all_pass:
                break
            
            # Check relational constraints if provided
            if constraints:
                constraints_ok = True
                for constraint in constraints:
                    if not constraint.check(source_objects, bound_objects):
                        constraints_ok = False
                        break
                if not constraints_ok:
                    evidence[ex_idx] = False
                    all_pass = False
                    break
            
            # Apply transformation and verify
            result = candidate_program.transformation_fn(source, bound_objects)
            if result != target:
                evidence[ex_idx] = False
                all_pass = False
            else:
                evidence[ex_idx] = True
        except Exception as e:
            evidence[ex_idx] = False
            all_pass = False
    
    return all_pass, evidence


# Distractor robustness testing (enhanced with relational constraints)
def test_distractor_robustness_enhanced(
    source: Grid,
    candidate_program: CandidateProgram,
    constraints: list[RelationalConstraint] | None = None,
    num_distractors: int = 2
) -> bool:
    """
    Test if candidate survives insertion of irrelevant distractor objects.
    Also checks that relational constraints still hold.
    """
    background = infer_background(source)
    objects = extract_objects(source, background_color=background)
    
    if len(objects) < 2:
        return True  # Not enough objects to test
    
    # Try adding distractor objects of various colors/shapes
    distractor_colors = [c for c in range(1, 10) 
                         if c != background and c not in {o.color for o in objects}][:num_distractors]
    
    for distractor_color in distractor_colors:
        h, w = len(source), len(source[0])
        for r in range(h):
            for c in range(w):
                if source[r][c] == background:
                    # Try placing distractor here
                    test_grid = [list(row) for row in source]
                    test_grid[r][c] = distractor_color
                    test_grid = tuple(tuple(row) for row in test_grid)
                    
                    try:
                        test_objects = extract_objects(test_grid, background_color=background)
                        bound_objects = {}
                        for binding in candidate_program.role_bindings:
                            matches = _matches(test_objects, binding.selector)
                            if len(matches) != 1:
                                return False  # Distractor broke the selector
                            bound_objects[binding.role] = matches[0]
                        
                        # Check constraints still hold
                        if constraints:
                            for constraint in constraints:
                                if not constraint.check(test_objects, bound_objects):
                                    return False
                        
                        candidate_program.transformation_fn(test_grid, bound_objects)
                    except Exception:
                        return False
    return True


# Ambiguity detection and handling
def detect_role_ambiguity(
    objects: list[ArcObject],
    role_candidates: dict[str, list[ArcObject]]
) -> tuple[bool, list[str]]:
    """
    Detect if there's ambiguity in role assignments.
    
    Returns:
        (is_ambiguous, list_of_ambiguity_reasons)
    """
    reasons = []
    
    for role, candidates in role_candidates.items():
        if len(candidates) > 1:
            # Check if candidates have identical relational signatures
            signatures = [compute_relational_signature(c, [c] + [o for o in objects if o.cells != c.cells]) 
                         for c in candidates]
            if len(set(str(s) for s in signatures)) == 1:
                reasons.append(f"Role '{role}' has {len(candidates)} candidates with identical relational signatures")
            else:
                # Check if they can be distinguished by some relational predicate
                distinguishable = False
                for i, c1 in enumerate(candidates):
                    for c2 in candidates[i+1:]:
                        if (c1.color != c2.color or 
                            c1.width != c2.width or 
                            c1.height != c2.height or
                            len(c1.cells) != len(c2.cells)):
                            distinguishable = True
                            break
                    if not distinguishable:
                        reasons.append(f"Role '{role}' has {len(candidates)} indistinguishable candidates")
    
    return len(reasons) > 0, reasons


# Enhanced role confidence with relational evidence
def _compute_role_confidence_enhanced(obj: ArcObject, role: str, 
                             all_objects: list[ArcObject], selector: Selector,
                             constraints: list[RelationalConstraint] | None = None) -> float:
    """Compute confidence score for a role assignment with relational evidence."""
    base_confidence = 1.0
    kind = selector[0]
    
    # Unique selectors are more confident
    if kind in ("unique-color", "unique-shape", "unique-size", "most-frequent-color", "least-frequent-color",
                "largest", "smallest", "point", "shape"):
        base_confidence += 0.5
    elif kind in ("largest", "smallest"):
        base_confidence += 0.3
    elif kind == "point":
        base_confidence += 0.2
    
    # Role-specific bonuses
    if role == "source":
        # Prefer objects with distinct shape (more likely to be copied)
        shape_counts = Counter(normalized_shape(o) for o in all_objects)
        if shape_counts[normalized_shape(obj)] == 1:
            base_confidence += 0.2
        # Prefer objects with distinctive relational signatures
        if hasattr(obj, 'relative_signature') and obj.relative_signature:
            base_confidence += 0.1
    elif role == "landmark":
        # Prefer stable, distinctive landmarks
        if kind in ("unique-color", "unique-shape", "unique-size", "largest", "smallest"):
            base_confidence += 0.3
        # Prefer objects with high connectivity to others (central in relation graph)
        if len(obj.adjacent_colors) > 0:
            base_confidence += 0.2
        # Prefer objects that participate in constraints
        if constraints:
            for c in constraints:
                if c.role_a == "landmark" or c.role_b == "landmark":
                    base_confidence += 0.1
    elif role == "anchor":
        # Prefer unique, stable anchors
        if kind in ("unique-color", "unique-shape", "unique-size"):
            base_confidence += 0.5
    
    # Bonus for constraint participation
    if constraints:
        for constraint in constraints:
            if constraint.role_a == role or constraint.role_b == role:
                base_confidence += 0.15
    
    # Penalty for objects that are enclosed (less likely to be independent landmarks)
    if len(obj.enclosed_by) > 0:
        base_confidence -= 0.2
    
    return min(base_confidence, 1.0)


# Cross-example consistency checker
def check_cross_example_consistency(
    train_pairs: list[tuple[Grid, Grid]],
    role: str,
    selector: Selector,
    constraints: list[RelationalConstraint] | None = None
) -> tuple[bool, float, dict]:
    """
    Check if a role selector is consistent across all training examples.
    
    Returns:
        (is_consistent, consistency_score, evidence_dict)
    """
    evidence = {}
    consistent_count = 0
    
    for ex_idx, (source, target) in enumerate(train_pairs):
        try:
            source_objects = extract_objects(source, background_color=infer_background(source))
            matches = _matches(source_objects, selector)
            
            if len(matches) == 1:
                # Check if constraints hold for this binding
                if constraints:
                    constraint_ok = True
                    for constraint in constraints:
                        if constraint.role_a == "source" or constraint.role_b == "source":
                            # Would need to resolve all bindings to check
                            pass
                evidence[ex_idx] = True
                consistent_count += 1
            else:
                evidence[ex_idx] = False
        except Exception:
            evidence[ex_idx] = False
    
    consistency_score = consistent_count / len(train_pairs) if train_pairs else 0.0
    return consistent_count == len(train_pairs), consistency_score, evidence
    """Cheap parsimony key for ranking relation hypotheses."""
    selector_bits: int
    placement_rank: int
    objects_touched: int
    recolor_penalty: int
    name: str  # tiebreaker


def _placement_rank(placement: tuple) -> int:
    """Rank placements by simplicity: onto_marker < adjacent < align_bbox < between < mirrored_across < repeated_k."""
    kind = placement[0]
    ranks = {
        "onto_marker": 0,
        "adjacent": 1,
        "align_bbox": 2,
        "between": 3,
        "mirrored_across": 4,
        "repeated_k": 5,
    }
    return ranks.get(kind, 99)


def _selector_bits(selector: Selector) -> int:
    """Bits needed to encode selector (fewer = simpler)."""
    kind = selector[0]
    # Single-token selectors are cheapest
    if kind in ("unique-color", "unique-shape", "unique-size", "most-frequent-color", "least-frequent-color",
                "largest", "smallest", "point", "shape"):
        return 1
    if kind in ("color", "area", "orientation"):
        return 2
    if kind == "color_shape":
        return 3
    return 4


def _compute_parsimony(rule: Rule, source_role: Selector, landmark_role: Selector,
                       landmark_b_role: Selector | None, placement: tuple,
                       color_policy: str) -> ParsimonyScore:
    """Compute parsimony score for a relation hypothesis."""
    selector_bits = (_selector_bits(source_role) + _selector_bits(landmark_role) +
                     (_selector_bits(landmark_b_role) if landmark_b_role else 0))
    placement_rank = _placement_rank(placement)
    # objects_touched: 2 for single landmark, 3 for between
    objects_touched = 3 if landmark_b_role else 2
    # recolor_penalty: 1 if copying with landmark color instead of source color
    recolor_penalty = 1 if color_policy == "landmark" else 0
    return ParsimonyScore(
        selector_bits=selector_bits,
        placement_rank=placement_rank,
        objects_touched=objects_touched,
        recolor_penalty=recolor_penalty,
        name=rule.name
    )


def _normalize_selector_name(selector: Selector) -> str:
    """Normalize selector for duplicate detection."""
    return selector[0]


def _funnel_hypotheses(rules: list[Rule], max_before_invariance: int = 16,
                       max_per_placement_family: int = 2) -> list[Rule]:
    """
    64 → 16 → 1 funnel applied ONLY to relation-conditioned-copy rules.
    Other rule families pass through unchanged.
    1. Score by parsimony (relation rules only)
    2. Drop exact duplicates (normalize selector names)
    3. Keep at most max_per_placement_family per placement family
    4. Keep at most max_before_invariance total relation rules
    """
    if not rules:
        return []
    
    # Separate relation-conditioned-copy rules from others
    relation_rules = [r for r in rules if r.family == "relation-conditioned-copy"]
    other_rules = [r for r in rules if r.family != "relation-conditioned-copy"]
    
    if not relation_rules:
        return rules  # No relation rules to funnel
    
    # Group by placement family and compute parsimony
    scored = []
    seen_normalized = set()
    
    for rule in relation_rules:
        # Parse placement family from name
        try:
            place_part = rule.name.split("->place(")[1].split(")->color")[0]
            placement_family = place_part.split(",")[-1].split(":")[0]
        except (IndexError, ValueError):
            placement_family = "unknown"
        
        # Normalize selector names for deduplication
        src_sel = _normalize_selector_name_from_rule(rule, "copy")
        lm_sel = _normalize_selector_name_from_rule(rule, "place")
        
        norm_key = (src_sel, lm_sel, placement_family, 
                    "landmark_b" in rule.name, rule.family)
        
        if norm_key in seen_normalized:
            continue
        seen_normalized.add(norm_key)
        
        scored.append((rule, placement_family))
    
    # Sort by complexity (lower = simpler), then name
    scored.sort(key=lambda x: (x[0].complexity, x[0].name))
    
    # Cap per placement family
    family_counts: Counter[str] = Counter()
    filtered = []
    for rule, family in scored:
        if family_counts[family] >= max_per_placement_family:
            continue
        filtered.append(rule)
        family_counts[family] += 1
        if len(filtered) >= max_before_invariance:
            break
    
    # Return other rules + funneled relation rules
    return other_rules + filtered


def _normalize_selector_name_from_rule(rule: Rule, prefix: str) -> str:
    """Extract and normalize selector from rule name."""
    try:
        if prefix == "copy":
            part = rule.name.split("object-program:copy(")[1].split(")")[0]
        else:
            part = rule.name.split("->place(")[1].split(",")[0]
        # Normalize: just take the selector kind
        return part.split(",")[0].strip("'\"()")
    except (IndexError, ValueError):
        return "unknown"


def _select_final_candidates(rules: list[Rule]) -> list[Rule]:
    """
    After invariance filtering, keep 1 primary + 1 distinct backup.
    Backup must differ in placement family or selector kind.
    """
    if not rules:
        return []
    if len(rules) == 1:
        return rules
    
    primary = rules[0]
    primary_family = _extract_placement_family(primary.name)
    primary_selector = _extract_source_selector(primary.name)
    
    for rule in rules[1:]:
        if (_extract_placement_family(rule.name) != primary_family or
            _extract_source_selector(rule.name) != primary_selector):
            return [primary, rule]
    
    return [primary]


def _extract_placement_family(name: str) -> str:
    try:
        return name.split("->place(")[1].split(")->color")[0].split(",")[-1].split(":")[0]
    except (IndexError, ValueError):
        return "unknown"


def _extract_source_selector(name: str) -> str:
    try:
        return name.split("object-program:copy(")[1].split(")")[0].split(",")[0].strip("'\"()")
    except (IndexError, ValueError):
        return "unknown"


def _matches(objects: Iterable[ArcObject], selector: Selector) -> list[ArcObject]:
    objects = list(objects)
    kind = selector[0]
    if kind == "shape":
        return [obj for obj in objects if normalized_shape(obj) == selector[1]]
    if kind == "color_shape":
        return [obj for obj in objects if obj.color == selector[1] and
                normalized_shape(obj) == selector[2]]
    if kind == "color":
        return [obj for obj in objects if obj.color == selector[1]]
    if kind == "area":
        return [obj for obj in objects if len(obj.cells) == selector[1]]
    if kind == "orientation":
        return [obj for obj in objects if obj.orientation == selector[1]]
    if kind == "point":
        return [obj for obj in objects if len(obj.cells) == 1]
    if kind in ("largest", "smallest"):
        if not objects:
            return []
        area = max if kind == "largest" else min
        target_area = area(len(obj.cells) for obj in objects)
        return [obj for obj in objects if len(obj.cells) == target_area]
    if kind == "unique-color":
        color_counts = Counter(obj.color for obj in objects)
        return [obj for obj in objects if color_counts[obj.color] == 1]
    if kind == "unique-shape":
        shape_counts = Counter(normalized_shape(obj) for obj in objects)
        return [obj for obj in objects if shape_counts[normalized_shape(obj)] == 1]
    if kind == "unique-size":
        size_counts = Counter(len(obj.cells) for obj in objects)
        return [obj for obj in objects if size_counts[len(obj.cells)] == 1]
    if kind == "most-frequent-color":
        if not objects:
            return []
        color_counts = Counter(obj.color for obj in objects)
        max_count = max(color_counts.values())
        target_colors = {c for c, cnt in color_counts.items() if cnt == max_count}
        return [obj for obj in objects if obj.color in target_colors]
    if kind == "least-frequent-color":
        if not objects:
            return []
        color_counts = Counter(obj.color for obj in objects)
        min_count = min(color_counts.values())
        target_colors = {c for c, cnt in color_counts.items() if cnt == min_count}
        return [obj for obj in objects if obj.color in target_colors]
    raise ValueError(f"unknown object selector: {kind}")


def _selector_specs(objects: list[ArcObject], obj: ArcObject) -> list[Selector]:
    """Return invariant object-role descriptions that uniquely select obj."""
    shape = normalized_shape(obj)
    candidates: list[Selector] = [
        ("shape", shape), ("color_shape", obj.color, shape),
        ("color", obj.color), ("area", len(obj.cells)),
        ("orientation", obj.orientation),
    ]
    if len(obj.cells) == 1:
        candidates.append(("point",))
    areas = [len(item.cells) for item in objects]
    if areas.count(len(obj.cells)) == 1:
        if len(obj.cells) == max(areas):
            candidates.append(("largest",))
        if len(obj.cells) == min(areas):
            candidates.append(("smallest",))
    color_counts = Counter(item.color for item in objects)
    if color_counts[obj.color] == 1:
        candidates.append(("unique-color",))
    shape_counts = Counter(normalized_shape(item) for item in objects)
    if shape_counts[shape] == 1:
        candidates.append(("unique-shape",))
    if areas.count(len(obj.cells)) == 1:
        candidates.append(("unique-size",))
    max_color_count = max(color_counts.values())
    if color_counts[obj.color] == max_color_count:
        candidates.append(("most-frequent-color",))
    min_color_count = min(color_counts.values())
    if color_counts[obj.color] == min_color_count:
        candidates.append(("least-frequent-color",))
    return list(dict.fromkeys(selector for selector in candidates
                              if (matches := _matches(objects, selector)) == [obj]))


def _selector_complexity(selector: Selector) -> int:
    return {"shape": 1, "point": 1, "largest": 1, "smallest": 1,
            "unique-color": 1, "unique-shape": 1, "unique-size": 1,
            "most-frequent-color": 1, "least-frequent-color": 1,
            "color": 2, "area": 2, "orientation": 2,
            "color_shape": 3}[selector[0]]


def _resolve(grid: Grid, selector: Selector) -> ArcObject:
    objects = extract_objects(grid, background_color=infer_background(grid))
    matches = _matches(objects, selector)
    if len(matches) != 1:
        raise ValueError("object role is absent or ambiguous")
    return matches[0]


def _shape_anchor(obj: ArcObject, choice: str) -> tuple[int, int]:
    top, left, _, _ = obj.bbox
    local = {(r - top, c - left) for r, c in obj.cells}
    if choice == "top_left":
        return min(local)
    if choice == "bottom_right":
        return max(local)
    if choice == "center_cell":
        center = obj.centroid
        return min(local, key=lambda point: (
            abs(point[0] + top - center[0]) + abs(point[1] + left - center[1]),
            point))
    raise ValueError(f"unknown source anchor: {choice}")


def _aligned_offset(source_size: int, landmark_size: int,
                    alignment: str) -> int | None:
    if alignment == "start":
        return 0
    if alignment == "end":
        return landmark_size - source_size
    difference = landmark_size - source_size
    if difference % 2:
        return None
    return difference // 2


def _placement_origin(source: ArcObject, landmark: ArcObject,
                      placement: tuple, landmark_b: ArcObject | None = None) -> tuple[int, int] | None:
    kind = placement[0]
    sr, sc, sr1, sc1 = source.bbox
    lr, lc, lr1, lc1 = landmark.bbox
    if kind == "onto_marker":
        _, anchor_name = placement
        ar, ac = _shape_anchor(source, anchor_name)
        marker_r, marker_c = min(landmark.cells)
        return marker_r - ar, marker_c - ac
    if kind == "align_bbox":
        _, vertical, horizontal = placement
        dy = _aligned_offset(source.height, landmark.height, vertical)
        dx = _aligned_offset(source.width, landmark.width, horizontal)
        if dy is None or dx is None:
            return None
        return lr + dy, lc + dx
    if kind == "adjacent":
        _, direction, alignment = placement
        if direction in ("above", "below"):
            dx = _aligned_offset(source.width, landmark.width, alignment)
            if dx is None:
                return None
            row = lr - source.height if direction == "above" else lr1
            return row, lc + dx
        dy = _aligned_offset(source.height, landmark.height, alignment)
        if dy is None:
            return None
        col = lc - source.width if direction == "left" else lc1
        return lr + dy, col
    if kind == "between":
        if landmark_b is None:
            return None
        br, bc, br1, bc1 = landmark_b.bbox
        mid_r = (lr + br) // 2
        mid_c = (lc + bc) // 2
        return mid_r - source.height // 2, mid_c - source.width // 2
    if kind == "mirrored_across":
        center_r = (lr + lr1) / 2
        center_c = (lc + lc1) / 2
        source_center_r = (sr + sr1) / 2
        source_center_c = (sc + sc1) / 2
        dy = int(2 * (center_r - source_center_r))
        dx = int(2 * (center_c - source_center_c))
        return sr + dy, sc + dx
    if kind == "repeated_k":
        _, k = placement
        dr = lr - sr
        dc = lc - sc
        return sr + k * dr, sc + k * dc
    return None


def _render_copy(grid: Grid, source_selector: Selector,
                 landmark_selector: Selector, placement: tuple,
                 color_policy: str, landmark_b_selector: Selector | None = None) -> Grid:
    source = _resolve(grid, source_selector)
    landmark = _resolve(grid, landmark_selector)
    if source.cells == landmark.cells:
        raise ValueError("source and landmark roles resolve to the same object")
    landmark_b = None
    if landmark_b_selector is not None:
        landmark_b = _resolve(grid, landmark_b_selector)
        if landmark_b.cells == source.cells or landmark_b.cells == landmark.cells:
            raise ValueError("landmark_b resolves to source or landmark")
    origin = _placement_origin(source, landmark, placement, landmark_b)
    if origin is None:
        raise ValueError("relation cannot be instantiated on this grid")
    top, left = source.bbox[:2]
    kind = placement[0]
    color = source.color if color_policy == "source" else landmark.color
    h, w = len(grid), len(grid[0])
    out = [list(row) for row in grid]
    background = infer_background(grid)

    def paint_cells(cells: frozenset[tuple[int, int]]) -> None:
        for r, c in cells:
            existing = grid[r][c]
            on_landmark = (r, c) in landmark.cells
            on_landmark_b = landmark_b is not None and (r, c) in landmark_b.cells
            if (r, c) in source.cells:
                raise ValueError("relation-conditioned copy overlaps its source")
            if existing != background and not on_landmark and not on_landmark_b and existing != color:
                raise ValueError("relation-conditioned copy collides with another object")
            out[r][c] = color

    if kind == "repeated_k":
        _, k = placement
        dr = origin[0] - top
        dc = origin[1] - left
        for i in range(1, k + 1):
            copy_cells = frozenset((r + i * dr, c + i * dc) for r, c in source.cells)
            if any(not (0 <= r < h and 0 <= c < w) for r, c in copy_cells):
                raise ValueError("repeated copy exceeds the canvas")
            paint_cells(copy_cells)
    else:
        dy, dx = origin[0] - top, origin[1] - left
        copied_cells = frozenset((r + dy, c + dx) for r, c in source.cells)
        if copied_cells == source.cells:
            raise ValueError("copy placement is a no-op")
        if any(not (0 <= r < h and 0 <= c < w) for r, c in copied_cells):
            raise ValueError("relation-conditioned copy exceeds the canvas")
        paint_cells(copied_cells)
    return tuple(tuple(row) for row in out)


def _check_landmark_translation(grid: Grid, source_selector: Selector,
                                landmark_selector: Selector,
                                placement: tuple, color_policy: str,
                                landmark_b_selector: Selector | None = None) -> bool | None:
    """Translate the landmark and check that the compiled placement follows."""
    background = infer_background(grid)
    objects = extract_objects(grid, background_color=background)
    source_matches = _matches(objects, source_selector)
    landmark_matches = _matches(objects, landmark_selector)
    if len(source_matches) != 1 or len(landmark_matches) != 1:
        return None
    source, landmark = source_matches[0], landmark_matches[0]
    landmark_b = None
    if landmark_b_selector is not None:
        landmark_b_matches = _matches(objects, landmark_b_selector)
        if len(landmark_b_matches) != 1:
            return None
        landmark_b = landmark_b_matches[0]
    original_origin = _placement_origin(source, landmark, placement, landmark_b)
    if original_origin is None:
        return None
    source_top, source_left = source.bbox[:2]
    kind = placement[0]
    if kind == "repeated_k":
        _, k = placement
        dr = original_origin[0] - source_top
        dc = original_origin[1] - source_left
        baseline_cells = frozenset()
        for i in range(1, k + 1):
            baseline_cells |= frozenset((r + i * dr, c + i * dc) for r, c in source.cells)
    else:
        baseline_cells = frozenset((r + original_origin[0] - source_top,
                                    c + original_origin[1] - source_left)
                                   for r, c in source.cells)
    h, w = len(grid), len(grid[0])
    other_cells = set().union(*(obj.cells for obj in objects
                                if obj.cells != landmark.cells))
    attempted = False
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        moved = frozenset((r + dy, c + dx) for r, c in landmark.cells)
        if any(not (0 <= r < h and 0 <= c < w) for r, c in moved):
            continue
        if moved & other_cells:
            continue
        attempted = True
        perturbed = [list(row) for row in grid]
        for r, c in landmark.cells:
            perturbed[r][c] = background
        for r, c in moved:
            perturbed[r][c] = landmark.color
        perturbed_grid = tuple(tuple(row) for row in perturbed)
        try:
            moved_source = _resolve(perturbed_grid, source_selector)
            moved_landmark = _resolve(perturbed_grid, landmark_selector)
            moved_landmark_b = None
            if landmark_b_selector is not None:
                moved_landmark_b_matches = _matches(
                    extract_objects(perturbed_grid, background_color=background),
                    landmark_b_selector)
                if len(moved_landmark_b_matches) != 1:
                    continue
                moved_landmark_b = moved_landmark_b_matches[0]
            origin = _placement_origin(moved_source, moved_landmark, placement, moved_landmark_b)
            if origin is None:
                continue
            top, left = moved_source.bbox[:2]
            if kind == "repeated_k":
                _, k = placement
                dr = origin[0] - top
                dc = origin[1] - left
                copy_cells = frozenset()
                for i in range(1, k + 1):
                    copy_cells |= frozenset((r + i * dr, c + i * dc) for r, c in moved_source.cells)
            else:
                copy_cells = frozenset((r + origin[0] - top,
                                        c + origin[1] - left)
                                       for r, c in moved_source.cells)
            if copy_cells == baseline_cells:
                continue
            output = _render_copy(perturbed_grid, source_selector,
                                  landmark_selector, placement, color_policy,
                                  landmark_b_selector)
            color = (moved_source.color if color_policy == "source"
                     else moved_landmark.color)
            if all(output[r][c] == color for r, c in copy_cells):
                return True
        except (ArithmeticError, IndexError, TypeError, ValueError):
            continue
    return False if attempted else None


def _placement_specs(source: ArcObject) -> list[tuple]:
    specs = [("onto_marker", anchor) for anchor in
             ("top_left", "center_cell", "bottom_right")]
    for vertical in ("start", "center", "end"):
        for horizontal in ("start", "center", "end"):
            specs.append(("align_bbox", vertical, horizontal))
    for direction in ("above", "below", "left", "right"):
        orthogonal = ("start", "center", "end")
        specs.extend(("adjacent", direction, align) for align in orthogonal)
    # Between two landmarks: place source between landmark_a and landmark_b
    specs.append(("between",))
    # Mirrored across a landmark (point reflection through landmark center)
    specs.append(("mirrored_across",))
    # Repeated k times in a line from landmark
    for k in (2, 3):
        specs.append(("repeated_k", k))
    return specs


def generate_relation_copy_hypotheses(
        train_pairs: Iterable[tuple[Grid, Grid]], *,
        max_hypotheses: int = 64) -> list[Rule]:
    """Compile copy/place candidates from object roles and landmark relations.

    No displacement is learned as a constant. Placement is represented as an
    anchor, bbox alignment, adjacency, between, mirrored, or repeated relation
    and is recomputed on each grid. The first demonstration prunes proposals;
    the caller must replay all demos.

    Returns at most 16 hypotheses after parsimony funnel (64 -> 16).
    """
    pairs = tuple(train_pairs)
    if len(pairs) < 2:
        return []
    first_source, first_target = pairs[0]
    deltas = [compare_grids(source, target, infer_background(source))
              for source, target in pairs]
    if any(delta.dimensions_changed or delta.removed_cells for delta in deltas):
        return []
    if not any(delta.added_cells or delta.recolored_cells for delta in deltas):
        return []

    objects = extract_objects(first_source,
                              background_color=infer_background(first_source))
    proposals: dict[str, Rule] = {}
    for source_object in objects:
        source_roles = _selector_specs(objects, source_object)
        if not source_roles:
            continue
        for landmark_object in objects:
            if landmark_object.cells == source_object.cells:
                continue
            landmark_roles = _selector_specs(objects, landmark_object)
            if not landmark_roles:
                continue
            for source_role in source_roles:
                for landmark_role in landmark_roles:
                    for placement in _placement_specs(source_object):
                        kind = placement[0]
                        # Between requires a second landmark
                        if kind == "between":
                            for landmark_b_object in objects:
                                if (landmark_b_object.cells == source_object.cells or
                                    landmark_b_object.cells == landmark_object.cells):
                                    continue
                                landmark_b_roles = _selector_specs(objects, landmark_b_object)
                                if not landmark_b_roles:
                                    continue
                                for landmark_b_role in landmark_b_roles:
                                    for color_policy in ("source", "landmark"):
                                        _add_proposal(proposals, source_role, landmark_role,
                                                      landmark_b_role, placement,
                                                      color_policy, source_object,
                                                      landmark_object, landmark_b_object,
                                                      first_source, first_target,
                                                      max_hypotheses)
                        else:
                            for color_policy in ("source", "landmark"):
                                _add_proposal(proposals, source_role, landmark_role,
                                              None, placement, color_policy,
                                              source_object, landmark_object, None,
                                              first_source, first_target,
                                              max_hypotheses)
                        if len(proposals) >= max_hypotheses:
                            break
                if len(proposals) >= max_hypotheses:
                    break
        if len(proposals) >= max_hypotheses:
            break
    
    raw_rules = list(proposals.values())
    # Apply 64 -> 16 funnel before invariance checking
    funneled = _funnel_hypotheses(raw_rules, max_before_invariance=16, max_per_placement_family=2)
    return funneled


def _add_proposal(proposals: dict[str, Rule],
                  source_role: Selector, landmark_role: Selector,
                  landmark_b_role: Selector | None,
                  placement: tuple, color_policy: str,
                  source_object, landmark_object, landmark_b_object,
                  first_source: Grid, first_target: Grid,
                  max_hypotheses: int) -> None:
    kind = placement[0]
    relation_names = ["source-role", "landmark-role"]
    if kind == "onto_marker":
        relation_names.append("copy_onto_marker")
    elif kind == "align_bbox":
        relation_names.append("align_bbox")
    elif kind == "adjacent":
        relation_names.append("adjacent")
    elif kind == "between":
        relation_names.append("between")
    elif kind == "mirrored_across":
        relation_names.append("mirrored_across")
    elif kind == "repeated_k":
        relation_names.append("repeated_k")
    else:
        relation_names.append("place_relative_to_landmark")
    readable_placement = ":".join(map(str, placement))
    name_parts = ["object-program:copy(" + repr(source_role),
                  ")->place(" + repr(landmark_role)]
    if landmark_b_role is not None:
        name_parts.append("," + repr(landmark_b_role))
    name_parts.append("," + readable_placement + ")->color(" + color_policy + ")")
    name = "".join(name_parts)
    if name in proposals:
        return
    apply = lambda grid, sr=source_role, lr=landmark_role, \
        lbr=landmark_b_role, place=placement, cp=color_policy: _render_copy(
            grid, sr, lr, place, cp, lbr)
    try:
        if apply(first_source) != first_target:
            return
    except (ArithmeticError, IndexError, TypeError, ValueError):
        return
    known_colors = {source_object.color, landmark_object.color}
    if landmark_b_object is not None:
        known_colors.add(landmark_b_object.color)
    proposals[name] = Rule(
        name=name, apply=apply,
        complexity=(4 + len(relation_names) +
                    _selector_complexity(source_role) +
                    _selector_complexity(landmark_role) +
                    (_selector_complexity(landmark_b_role) if landmark_b_role else 0)),
        assumptions=1,
        family="relation-conditioned-copy",
        structural_coverage=len(relation_names),
        known_colors=tuple(sorted(known_colors)),
        relation_predicates=tuple(relation_names),
        relation_perturbation=lambda grid, sr=source_role, lr=landmark_role,
            lbr=landmark_b_role, place=placement, cp=color_policy:
            _check_landmark_translation(grid, sr, lr, place, cp, lbr))
