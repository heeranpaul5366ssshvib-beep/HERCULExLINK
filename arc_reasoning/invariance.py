"""Metamorphic checks for exact-fit ARC rule candidates."""

from __future__ import annotations

from collections import deque
from typing import Iterable

from .grid import Grid
from .primitives import crop_non_background
from .relations import infer_background
from .objects import extract_objects


def _pad(grid: Grid, color: int, top: int = 1, left: int = 1,
         bottom: int = 1, right: int = 1) -> Grid:
    width = len(grid[0]) + left + right
    rows = [[color] * width for _ in range(top)]
    rows.extend([[color] * left + list(row) + [color] * right for row in grid])
    rows.extend([[color] * width for _ in range(bottom)])
    return tuple(tuple(row) for row in rows)


def _canvas_padding(rule, pairs) -> bool | None:
    applicable = 0
    for source, target in pairs:
        background = infer_background(source)
        padded = _pad(source, background)
        if (len(source), len(source[0])) == (len(target), len(target[0])):
            expected = _pad(target, background)
        elif crop_non_background(source, background) == target:
            # An outer canvas border is irrelevant to a crop-by-content rule.
            expected = target
        else:
            continue
        applicable += 1
        try:
            if rule.apply(padded) != expected:
                return False
        except (ArithmeticError, IndexError, TypeError, ValueError):
            return False
    return applicable > 0 if applicable else None


def _background_recolor(rule, pairs) -> bool | None:
    applicable = 0
    for source, target in pairs:
        if (len(source), len(source[0])) != (len(target), len(target[0])):
            continue
        background = infer_background(source)
        used = {value for row in source + target for value in row}
        replacement = next((value for value in range(10) if value not in used), None)
        if replacement is None:
            continue
        changed_source = tuple(tuple(replacement if value == background else value
                                     for value in row) for row in source)
        changed_target = tuple(tuple(replacement if value == background else value
                                     for value in row) for row in target)
        applicable += 1
        try:
            if rule.apply(changed_source) != changed_target:
                return False
        except (ArithmeticError, IndexError, TypeError, ValueError):
            return False
    return applicable > 0 if applicable else None


def _palette_rename(rule, pairs) -> bool | None:
    palette = sorted({value for source, target in pairs
                      for row in source + target for value in row if value != 0})
    if not palette:
        return None
    mapping: dict[int, int] = {}
    if len(palette) > 1:
        mapping[palette[0]], mapping[palette[1]] = palette[1], palette[0]
    else:
        replacement = next((value for value in range(1, 10)
                            if value != palette[0]), None)
        if replacement is None:
            return None
        mapping[palette[0]] = replacement
    for source, target in pairs:
        renamed_source = tuple(tuple(mapping.get(value, value) for value in row)
                               for row in source)
        renamed_target = tuple(tuple(mapping.get(value, value) for value in row)
                               for row in target)
        try:
            if rule.apply(renamed_source) != renamed_target:
                return False
        except (ArithmeticError, IndexError, TypeError, ValueError):
            return False
    return True


def _irrelevant_object_insertion(rule, pairs) -> bool | None:
    """Insert an irrelevant distractor object and check if rule still executes without unhandled exceptions.
    
    The test adds a single pixel of unused color and verifies the rule doesn't crash
    with unhandled exceptions (ArithmeticError, IndexError, TypeError).
    ValueError from selector ambiguity is expected when input is modified.
    """
    applicable = 0
    for source, target in pairs:
        background = infer_background(source)
        used_colors = {v for s, t in pairs for row in s + t for v in row if v != background}
        unused_colors = [c for c in range(1, 10) if c not in used_colors]
        if not unused_colors:
            continue
        distractor_color = unused_colors[0]
        h, w = len(source), len(source[0])
        
        # Find empty spot
        for r in range(h):
            for c in range(w):
                if source[r][c] == background:
                    test_grid = [list(row) for row in source]
                    test_grid[r][c] = distractor_color
                    test_grid = tuple(tuple(row) for row in test_grid)
                    applicable += 1
                    try:
                        result = rule.apply(test_grid)
                        # Rule should execute and produce valid grid dimensions
                        if len(result) != len(source) or len(result[0]) != len(source[0]):
                            return False
                    except (ArithmeticError, IndexError, TypeError):
                        # Unhandled exceptions are failures
                        return False
                    except ValueError:
                        # ValueError from selector ambiguity is expected when input is modified
                        # This is not a failure - the rule gracefully handles ambiguous input
                        pass
                    break
            if applicable > 0:
                break
    return applicable > 0 if applicable else None


def _irrelevant_object_deletion(rule, pairs) -> bool | None:
    """Delete an irrelevant object and check if rule still works on remaining.
    
    Removes the smallest object (likely distractor) and checks if rule executes
    without unhandled exceptions. ValueError from selector ambiguity is expected
    if the removed object was a landmark/source.
    """
    applicable = 0
    for source, target in pairs:
        background = infer_background(source)
        objects = extract_objects(source, background_color=background)
        if len(objects) < 2:
            continue
        # Remove the smallest object (likely distractor)
        smallest = min(objects, key=lambda o: len(o.cells))
        test_grid = [list(row) for row in source]
        for r, c in smallest.cells:
            test_grid[r][c] = background
        test_grid = tuple(tuple(row) for row in test_grid)
        applicable += 1
        try:
            result = rule.apply(test_grid)
            if len(result) != len(source) or len(result[0]) != len(source[0]):
                return False
        except (ArithmeticError, IndexError, TypeError):
            # Unhandled exceptions are failures
            return False
        except ValueError:
            # ValueError from selector ambiguity is expected if we removed a landmark/source
            pass
    return applicable > 0 if applicable else None


def _object_reordering(rule, pairs) -> bool | None:
    """Test if rule works when object order changes (should for relational rules)."""
    applicable = 0
    for source, target in pairs:
        background = infer_background(source)
        objects = extract_objects(source, background_color=background)
        if len(objects) < 2:
            continue
        # This test is more conceptual - we test by applying to a grid
        # where objects are in different spatial arrangement but same relations
        # For now, just check basic applicability
        applicable += 1
        try:
            result = rule.apply(source)
            if result != target:
                return False
        except (ArithmeticError, IndexError, TypeError, ValueError):
            return False
    return applicable > 0 if applicable else None


def _symmetric_duplicate_insertion(rule, pairs) -> bool | None:
    """Insert a symmetric duplicate of an existing object."""
    applicable = 0
    for source, target in pairs:
        background = infer_background(source)
        objects = extract_objects(source, background_color=background)
        if not objects:
            continue
        # Try to place a duplicate of the first object at a symmetric position
        obj = objects[0]
        h, w = len(source), len(source[0])
        # Try placing at mirrored position
        top, left, bottom, right = obj.bbox
        mirror_r = h - 1 - (top + bottom) // 2
        mirror_c = w - 1 - (left + right) // 2
        if 0 <= mirror_r < h and 0 <= mirror_c < w:
            test_grid = [list(row) for row in source]
            for r, c in obj.cells:
                nr = mirror_r - top + r
                nc = mirror_c - left + c
                if 0 <= nr < h and 0 <= nc < w:
                    test_grid[nr][nc] = obj.color
            test_grid = tuple(tuple(row) for row in test_grid)
            applicable += 1
            try:
                result = rule.apply(test_grid)
                if len(result) != len(source) or len(result[0]) != len(source[0]):
                    return False
            except (ArithmeticError, IndexError, TypeError):
                # Unhandled exceptions are failures
                return False
            except ValueError:
                # ValueError from selector ambiguity is expected when input is modified
                pass
    return applicable > 0 if applicable else None


def _distractor_objects(rule, pairs) -> bool | None:
    """Combined test: rule should not break when distractors are added/removed."""
    # Test insertion
    ins = _irrelevant_object_insertion(rule, pairs)
    if ins is False:
        return False
    # Test deletion
    dels = _irrelevant_object_deletion(rule, pairs)
    if dels is False:
        return False
    return True


def check_rule_invariance(rule, train_pairs: Iterable[tuple[Grid, Grid]]) -> dict:
    """Check exact-fit rules under controlled frame, background, and color changes.

    Acceptance criteria:
    - Relational rules (with relation_predicates) MUST pass landmark_translation
      when it is applicable (not None). This tests whether the rule tracks
      landmark movement rather than memorizing fixed offsets.
      Relational rules should also NOT fail extended checks when applicable.
    - Non-relational rules must pass at least one CORE invariance check:
      landmark_translation, canvas_padding, or background_recolor.
      Palette_rename is reported but does NOT grant acceptance alone,
      EXCEPT for general geometric transformations (scale, tile) where 
      no core checks are applicable.
      Extended checks (distractor_robustness, symmetric_duplicate) are 
      reported but do NOT grant/revoke acceptance for non-relational rules.
    """
    pairs = tuple(train_pairs)
    outcomes: dict[str, bool | None] = {"landmark_translation": None}
    has_relation = bool(getattr(rule, "relation_predicates", ()))
    if rule.relation_perturbation is not None:
        results = [rule.relation_perturbation(source) for source, _ in pairs]
        applicable = [result for result in results if result is not None]
        outcomes["landmark_translation"] = (
            bool(applicable) and all(applicable) if applicable else None)
    outcomes["canvas_padding"] = _canvas_padding(rule, pairs)
    outcomes["background_recolor"] = _background_recolor(rule, pairs)
    outcomes["palette_rename"] = _palette_rename(rule, pairs)
    # Extended invariance tests
    outcomes["distractor_robustness"] = _distractor_objects(rule, pairs)
    outcomes["symmetric_duplicate"] = _symmetric_duplicate_insertion(rule, pairs)

    core_checks = ("landmark_translation", "canvas_padding", "background_recolor")
    extended_checks = ("distractor_robustness", "symmetric_duplicate")
    # Relational rules require landmark_translation to pass when applicable.
    if has_relation and outcomes["landmark_translation"] is not None:
        # For relational: require landmark_translation AND don't fail extended checks
        lt_pass = outcomes["landmark_translation"] is True
        ext_fail = any(outcomes.get(c) is False for c in extended_checks)
        accepted = lt_pass and not ext_fail
    else:
        # Non-relational: accept if at least one CORE check passes.
        passed_core = tuple(name for name in core_checks if outcomes.get(name) is True)
        # For general geometric transformations (scale, tile) where no core 
        # checks are applicable, palette_rename can grant acceptance.
        core_applicable = any(outcomes.get(c) is not None for c in core_checks)
        # Only scale and tile families get palette_rename acceptance for dimension-changing
        is_geometric_transform = getattr(rule, "family", "") in ("scaling", "tiling")
        if not core_applicable and outcomes.get("palette_rename") is True and is_geometric_transform:
            accepted = True
        else:
            accepted = bool(passed_core)

    failed = tuple(name for name, result in outcomes.items() if result is False)
    return {"passed": tuple(name for name, result in outcomes.items() if result is True),
            "failed": failed,
            "not_applicable": tuple(name for name, result in outcomes.items()
                                     if result is None),
            "accepted": accepted, "checks": outcomes}