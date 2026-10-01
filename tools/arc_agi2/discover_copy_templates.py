"""Aggregate-only copy-pattern audit over demonstrations in a dev split."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from arc_reasoning.deltas import compare_grids
from arc_reasoning.grid import parse_grid
from arc_reasoning.objects import extract_objects
from arc_reasoning.primitives import object_shape_signature
from arc_reasoning.rules import _object_copy_rule
from tools.arc_agi2.benchmark import load_split


def _addition_objects(source, target):
    delta = compare_grids(source, target)
    if delta.dimensions_changed or delta.removed_cells or delta.recolored_cells:
        return None
    cells = {(row, col): color for row, col, color in delta.added_cells}
    addition_grid = tuple(tuple(cells.get((row, col), 0)
                                for col in range(len(source[0])))
                          for row in range(len(source)))
    return extract_objects(addition_grid)


def discover(root: Path, manifest_name: str = "fresh_copy_split_manifest.json") -> dict:
    cases = load_split(root, "training_tasks", manifest_name)
    tasks = Counter()
    train_pairs = 0
    anchor_relative_consistent = 0
    for _name, _digest, task in cases:
        pairs = tuple((parse_grid(pair["input"]), parse_grid(pair["output"]))
                      for pair in task.get("train", []))
        if not pairs:
            continue
        train_pairs += len(pairs)
        every_demo_copylike = True
        any_demo_copylike = False
        anchor_plans: dict[tuple, tuple[int, int, int]] = {}
        anchor_plan_valid = True
        anchor_evidence: set[tuple] = set()
        for source, target in pairs:
            additions = _addition_objects(source, target)
            if additions is None or not additions:
                every_demo_copylike = False
                anchor_plan_valid = False
                continue
            source_objects = extract_objects(source)
            if not source_objects:
                every_demo_copylike = False
                anchor_plan_valid = False
                continue
            any_demo_copylike = True
            for added in additions:
                signature = object_shape_signature(added)
                matching = [obj for obj in source_objects
                            if object_shape_signature(obj) == signature]
                same_color = [obj for obj in matching if obj.color == added.color]
                if len(same_color) == 1:
                    original = same_color[0]
                elif len(matching) == 1:
                    original = matching[0]
                else:
                    every_demo_copylike = False
                    anchor_plan_valid = False
                    continue
                key = (original.color, signature)
                if len(source_objects) != 2:
                    anchor_plan_valid = False
                    continue
                anchors = [obj for obj in source_objects if obj is not original]
                if len(anchors) != 1:
                    anchor_plan_valid = False
                    continue
                anchor = anchors[0]
                anchor_key = (anchor.color, object_shape_signature(anchor))
                plan_key = (key, anchor_key)
                relative = (added.bbox[0] - anchor.bbox[0],
                            added.bbox[1] - anchor.bbox[1], added.color)
                if plan_key in anchor_plans and anchor_plans[plan_key] != relative:
                    anchor_plan_valid = False
                anchor_plans[plan_key] = relative
                anchor_evidence.add(plan_key)
        if any_demo_copylike:
            tasks["at_least_one_demo_adds_a_source_shape"] += 1
        if every_demo_copylike and any_demo_copylike:
            tasks["every_demo_preserves_and_adds_source_shapes"] += 1
        if _object_copy_rule(pairs) is not None:
            tasks["constant_source_relative_copy_rule_exactly_replays"] += 1
        if (anchor_plan_valid and anchor_evidence and
                len(anchor_evidence) == len(anchor_plans)):
            anchor_relative_consistent += 1
    return {
        "source": "official public training demonstrations only",
        "split_manifest": manifest_name,
        "task_count": len(cases),
        "training_pair_count": train_pairs,
        "task_patterns": dict(sorted(tasks.items())),
        "two_object_anchor_relative_consistency_count": anchor_relative_consistent,
        "interpretation_limit": "aggregate pattern inventory; not solver accuracy",
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--manifest", default="fresh_copy_split_manifest.json")
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/arc_agi2/copy_template_discovery.json"))
    args = parser.parse_args()
    result = discover(args.root, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
