"""Aggregate failure-shape diagnostics for the frozen internal split.

This writes feature counts only: no task grids, IDs, predicted answers, or
expected answers are copied into the artifact.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from arc_reasoning.grid import parse_grid
from arc_reasoning.objects import extract_objects
from tools.arc_agi2.benchmark import load_split


def _shape_multiset(grid):
    from arc_reasoning.primitives import object_shape_signature
    return Counter(object_shape_signature(obj) for obj in extract_objects(grid))


def _color_shape_multiset(grid):
    from arc_reasoning.primitives import object_shape_signature
    return Counter((obj.color, object_shape_signature(obj))
                   for obj in extract_objects(grid))


def diagnose(root: Path, score_path: Path) -> dict:
    report = json.loads(score_path.read_text("utf-8"))
    if report.get("split") != "validation_tasks":
        raise ValueError("diagnostic accepts only the frozen internal validation score")
    failed = {row["task_id"] for row in report["rows"] if not row["solved_pass2"]}
    no_rule = {row["task_id"] for row in report["rows"]
               if row["category"] == "no_verified_rule"}
    task_flags = Counter()
    pair_flags = Counter()
    training_pair_flags = Counter()
    consistent_demo_relations = Counter()
    object_template_flags = Counter()
    joint_template_flags = Counter()
    failed_pairs = 0
    no_rule_tasks_seen = 0
    for name, _digest, task in load_split(root, "validation_tasks"):
        task_id = Path(name).stem
        if task_id not in failed:
            continue
        if task_id in no_rule:
            no_rule_tasks_seen += 1
            demo_relations = {"dimensions": [], "foreground_delta": [],
                              "component_delta": []}
            demo_object_templates = []
            for pair in task.get("train", []):
                source = parse_grid(pair["input"])
                target = parse_grid(pair["output"])
                source_cells = sum(value != 0 for row in source for value in row)
                target_cells = sum(value != 0 for row in target for value in row)
                source_components = len(extract_objects(source))
                target_components = len(extract_objects(target))
                source_shapes = _shape_multiset(source)
                target_shapes = _shape_multiset(target)
                source_colored_shapes = _color_shape_multiset(source)
                target_colored_shapes = _color_shape_multiset(target)
                demo_object_templates.append({
                    "all_output_shapes_seen_in_input": all(
                        source_shapes[shape] > 0 for shape in target_shapes),
                    "all_output_colored_shapes_seen_in_input": all(
                        source_colored_shapes[key] > 0 for key in target_colored_shapes),
                    "shape_multiplicity_increased": any(
                        target_shapes[shape] > source_shapes[shape]
                        for shape in target_shapes),
                })
                demo_relations["dimensions"].append(
                    "same" if (len(source), len(source[0])) ==
                    (len(target), len(target[0])) else "changed")
                demo_relations["foreground_delta"].append(
                    "added" if target_cells > source_cells else
                    "removed" if target_cells < source_cells else "same")
                demo_relations["component_delta"].append(
                    "more" if target_components > source_components else
                    "fewer" if target_components < source_components else "same")
                flags = []
                if demo_relations["dimensions"][-1] == "same":
                    flags.append("same_demo_dimensions")
                flags.append(f"demo_foreground_{demo_relations['foreground_delta'][-1]}")
                flags.append(f"demo_components_{demo_relations['component_delta'][-1]}")
                training_pair_flags.update(flags)
            for relation, values in demo_relations.items():
                if values and len(set(values)) == 1:
                    consistent_demo_relations[f"all_demos_{relation}_{values[0]}"] += 1
            for feature in ("all_output_shapes_seen_in_input",
                            "all_output_colored_shapes_seen_in_input",
                            "shape_multiplicity_increased"):
                values = [profile[feature] for profile in demo_object_templates]
                if values and len(set(values)) == 1:
                    object_template_flags[f"all_demos_{feature}_{values[0]}"] += 1
            relation_values = {
                relation: (values[0] if values and len(set(values)) == 1 else "mixed")
                for relation, values in demo_relations.items()
            }
            joint_key = ",".join(f"{key}={relation_values[key]}"
                                  for key in sorted(relation_values))
            for feature in ("all_output_shapes_seen_in_input",
                            "all_output_colored_shapes_seen_in_input"):
                values = [profile[feature] for profile in demo_object_templates]
                if values and len(set(values)) == 1:
                    joint_template_flags[
                        f"{joint_key}|all_demos_{feature}={values[0]}"] += 1
            consistent_demo_relations[
                "joint:" + ",".join(f"{key}={relation_values[key]}"
                                    for key in sorted(relation_values))] += 1
        task_changed_shape_inventory = False
        for pair in task.get("test", []):
            source = parse_grid(pair["input"])
            target = parse_grid(pair["output"])
            flags = set()
            if (len(source), len(source[0])) == (len(target), len(target[0])):
                flags.add("same_grid_dimensions")
            source_cells = {(r, c): value for r, row in enumerate(source)
                            for c, value in enumerate(row) if value}
            target_cells = {(r, c): value for r, row in enumerate(target)
                            for c, value in enumerate(row) if value}
            if len(target_cells) > len(source_cells):
                flags.add("foreground_cells_added")
            elif len(target_cells) < len(source_cells):
                flags.add("foreground_cells_removed")
            if {v for row in source for v in row} == {v for row in target for v in row}:
                flags.add("same_palette")
            source_objects, target_objects = extract_objects(source), extract_objects(target)
            if len(target_objects) < len(source_objects):
                flags.add("fewer_output_components")
            if len(target_objects) > len(source_objects):
                flags.add("more_output_components")
            if _shape_multiset(source) == _shape_multiset(target):
                flags.add("same_object_shape_inventory")
            if _color_shape_multiset(source) == _color_shape_multiset(target):
                flags.add("same_colored_shape_inventory")
            if ("same_grid_dimensions" in flags and
                    "same_colored_shape_inventory" in flags):
                if any(a.bbox != b.bbox or a.cells != b.cells
                       for a, b in zip(source_objects, target_objects)):
                    flags.add("object_motion_or_repositioning")
            if "fewer_output_components" in flags and "foreground_cells_added" in flags:
                flags.add("line_or_bridge_or_object_merge")
            pair_flags.update(flags)
            failed_pairs += 1
            task_changed_shape_inventory |= "same_object_shape_inventory" in flags
        if task_changed_shape_inventory:
            task_flags["at_least_one_test_preserves_object_shape_inventory"] += 1
    return {
        "source": "frozen internal validation split only",
        "failed_task_count": len(failed),
        "failed_test_pair_count": failed_pairs,
        "no_verified_rule_task_count": no_rule_tasks_seen,
        "no_verified_rule_training_pair_flags": dict(sorted(training_pair_flags.items())),
        "no_verified_rule_consistent_demo_relations": dict(
            sorted(consistent_demo_relations.items())),
        "no_verified_rule_object_template_flags": dict(sorted(object_template_flags.items())),
        "no_verified_rule_joint_template_flags": dict(sorted(joint_template_flags.items())),
        "task_flags": dict(task_flags),
        "test_pair_flags": dict(sorted(pair_flags.items())),
        "interpretation_limit": "overlapping structural indicators; not exclusive failure causes",
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--score", type=Path,
                        default=Path("artifacts/arc_agi2/internal_validation_v10.json"))
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/arc_agi2/internal_failure_diagnostics.json"))
    args = parser.parse_args()
    result = diagnose(args.root, args.score)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
