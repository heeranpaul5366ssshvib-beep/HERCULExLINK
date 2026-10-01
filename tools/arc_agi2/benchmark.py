"""Leak-resistant task-level scoring for ARC public training subsets."""

from __future__ import annotations

import hashlib
import json
from time import perf_counter
from collections import Counter
from pathlib import Path

from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver


def load_split(root: Path, name: str,
               manifest_name: str = "internal_split_manifest.json") -> list[tuple[str, str, dict]]:
    data_root = root / "data" / "arc_agi2"
    manifest_path = Path(manifest_name)
    if not manifest_path.is_absolute():
        manifest_path = data_root / manifest_path
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if name not in ("training_tasks", "validation_tasks"):
        raise ValueError("internal benchmark may load only development or validation split")
    result = []
    for row in manifest[name]:
        path = data_root / "public_training" / row["file"]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row["sha256"]:
            raise ValueError(f"task hash changed after split freeze: {row['file']}")
        result.append((row["file"], digest, json.loads(raw)))
    return result


def score_task(solver: ArcSolver, task: dict,
               include_coverage: bool = False) -> dict:
    solved_top1 = 0
    solved_pass2 = 0
    cell_errors = []
    shape_errors = 0
    unexpected_color_cells = 0
    empty_candidates = 0
    output_count = 0
    inference_task = {
        "train": [{"input": pair["input"], "output": pair["output"]}
                  for pair in task.get("train", [])],
        "test": [{"input": pair["input"]} for pair in task.get("test", [])],
    }
    result = solver.solve(inference_task, include_coverage=include_coverage)
    for test_index, test in enumerate(task.get("test", [])):
        expected = parse_grid(test["output"])
        expected_colors = {value for row in expected for value in row}
        candidates = result["candidates"][test_index]
        output_count += 1
        if not candidates:
            empty_candidates += 1
            continue
        predicted = [candidate.grid for candidate in candidates[:2]]
        if predicted[0] == expected:
            solved_top1 += 1
        if expected in predicted:
            solved_pass2 += 1
        for candidate in predicted:
            if len(candidate) != len(expected) or len(candidate[0]) != len(expected[0]):
                shape_errors += 1
                continue
            unexpected_color_cells += sum(
                1 for row_a, row_b in zip(candidate, expected)
                for a, b in zip(row_a, row_b)
                if a != b and a not in expected_colors)
            cell_errors.append(sum(a != b for row_a, row_b in zip(candidate, expected)
                                   for a, b in zip(row_a, row_b)))
    score = {"top1_outputs": solved_top1, "pass2_outputs": solved_pass2,
             "output_count": output_count, "empty_candidates": empty_candidates,
             "shape_errors": shape_errors,
             "unexpected_color_cells": unexpected_color_cells,
             "cell_errors": cell_errors,
             "verified_rule_count": len(result["verified_rules"]),
             "rules": result["verified_rules"]}
    if include_coverage:
        score["hypothesis_coverage"] = result["hypothesis_coverage"]
    return score


def evaluate_internal(root: Path, split: str = "validation_tasks",
                      manifest_name: str = "internal_split_manifest.json",
                      task_limit: int | None = None) -> dict:
    started = perf_counter()
    cases = load_split(root, split, manifest_name)
    if task_limit is not None:
        if task_limit < 1:
            raise ValueError("task_limit must be positive")
        cases = cases[:task_limit]
    solver = ArcSolver()
    rows = []
    categories: Counter[str] = Counter()
    totals = Counter()
    coverage_statuses: Counter[str] = Counter()
    coverage_totals: Counter[str] = Counter()
    invariance_outcomes: dict[str, Counter[str]] = {
        name: Counter() for name in ("landmark_translation", "canvas_padding",
                                     "background_recolor", "palette_rename")}
    rule_taxonomy: dict[str, Counter[str]] = {
        "exact": Counter(), "invariance_surviving": Counter()}
    generated_families: Counter[str] = Counter()
    verified_families: Counter[str] = Counter()
    match_histogram: Counter[str] = Counter()
    search_reasons: Counter[str] = Counter()
    search_tasks_triggered = search_tasks_found_exact = 0
    search_expansions = search_elapsed = search_exact_programs = 0
    search_partial_programs = 0
    for name, digest, task in cases:
        score = score_task(solver, task, include_coverage=True)
        coverage = score["hypothesis_coverage"]
        coverage_totals.update({key: coverage[key] for key in (
            "generated_hypotheses", "verified_hypotheses", "rejected_hypotheses",
            "execution_error_hypotheses", "near_miss_hypotheses",
            "exact_training_hypotheses", "invariance_surviving_hypotheses",
            "invariance_rejected_hypotheses", "exact_local_rewrite_hypotheses",
            "invariance_surviving_local_rewrite_hypotheses",
            "exact_relation_hypotheses",
            "invariance_surviving_relation_hypotheses")})
        for check_name, outcomes in coverage.get(
                "invariance_check_outcomes", {}).items():
            invariance_outcomes.setdefault(check_name, Counter()).update(outcomes)
        for key, field in (("exact", "exact_rule_taxonomy"),
                           ("invariance_surviving", "invariance_surviving_rule_taxonomy")):
            rule_taxonomy[key].update(coverage.get(field, {}))
        coverage_statuses[coverage["status"]] += 1
        generated_families.update(coverage["families_generated"])
        verified_families.update(coverage["families_verified"])
        match_histogram.update(coverage["exact_demo_match_histogram"])
        search = coverage["program_search"]
        reason = search.get("reason")
        if reason is None:
            reason = f"termination:{search.get('termination', 'unknown')}"
        search_reasons[reason] += 1
        if search.get("triggered"):
            search_tasks_triggered += 1
            search_expansions += search.get("state_expansions", 0)
            search_elapsed += search.get("elapsed_seconds", 0.0)
            search_exact_programs += search.get("exact_programs_found", 0)
            search_partial_programs += search.get("emitted_partial_programs", 0)
            search_tasks_found_exact += int(search.get("exact_programs_found", 0) > 0)
        solved = score["pass2_outputs"] == score["output_count"]
        if not score["output_count"]:
            category = "invalid_no_test_pairs"
        elif solved:
            category = "solved"
        elif score["empty_candidates"] == score["output_count"]:
            category = "no_verified_rule"
        elif score["shape_errors"]:
            category = "output_shape"
        elif score["unexpected_color_cells"]:
            category = "unexpected_color"
        else:
            category = "wrong_cells_or_rule"
        categories[category] += 1
        totals.update({k: score[k] for k in (
            "top1_outputs", "pass2_outputs", "output_count", "empty_candidates",
            "shape_errors", "unexpected_color_cells")})
        rows.append({"task_id": Path(name).stem, "task_sha256": digest,
                     "solved_pass2": solved, "category": category,
                     "top1_outputs": score["top1_outputs"],
                     "pass2_outputs": score["pass2_outputs"],
                     "output_count": score["output_count"],
                     "verified_rule_count": score["verified_rule_count"],
                     "hypothesis_coverage": coverage,
                     "rules": score["rules"]})
    data_root = root / "data" / "arc_agi2"
    manifest_path = Path(manifest_name)
    if not manifest_path.is_absolute():
        manifest_path = data_root / manifest_path
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    solved_tasks = sum(row["solved_pass2"] for row in rows)
    return {
        "benchmark": "ARC-AGI-2 official public training tasks / internal split",
        "split": split,
        "split_manifest": manifest_path.name,
        "split_manifest_sha256": manifest_digest,
        "task_limit": task_limit,
        "evaluation_scope": "iterative_development_diagnostic",
        "solver_sha256": solver_digest(root),
        "elapsed_seconds": round(perf_counter() - started, 6),
        "task_count": len(rows),
        "solved_tasks": solved_tasks,
        "failed_tasks": len(rows) - solved_tasks,
        "task_accuracy": solved_tasks / len(rows) if rows else 0.0,
        "top1_test_outputs": totals["top1_outputs"],
        "pass2_test_outputs": totals["pass2_outputs"],
        "test_output_count": totals["output_count"],
        "failure_categories": dict(sorted(categories.items())),
        "hypothesis_coverage": {
            "generated_hypotheses": coverage_totals["generated_hypotheses"],
            "verified_hypotheses": coverage_totals["verified_hypotheses"],
            "exact_training_hypotheses": coverage_totals["exact_training_hypotheses"],
            "invariance_surviving_hypotheses":
                coverage_totals["invariance_surviving_hypotheses"],
            "invariance_rejected_hypotheses":
                coverage_totals["invariance_rejected_hypotheses"],
            "exact_local_rewrite_hypotheses":
                coverage_totals["exact_local_rewrite_hypotheses"],
            "invariance_surviving_local_rewrite_hypotheses":
                coverage_totals["invariance_surviving_local_rewrite_hypotheses"],
            "exact_relation_hypotheses":
                coverage_totals["exact_relation_hypotheses"],
            "invariance_surviving_relation_hypotheses":
                coverage_totals["invariance_surviving_relation_hypotheses"],
            "invariance_check_outcomes": {
                name: dict(sorted(counts.items()))
                for name, counts in sorted(invariance_outcomes.items())},
            "rule_taxonomy": {
                key: {name: counts.get(name, 0) for name in
                      ("relational", "local-rewrite", "crop-scale", "other")}
                for key, counts in rule_taxonomy.items()},
            "rejected_hypotheses": coverage_totals["rejected_hypotheses"],
            "execution_error_hypotheses": coverage_totals["execution_error_hypotheses"],
            "near_miss_hypotheses": coverage_totals["near_miss_hypotheses"],
            "task_status_counts": dict(sorted(coverage_statuses.items())),
            "families_generated": dict(sorted(generated_families.items())),
            "families_verified": dict(sorted(verified_families.items())),
            "program_search": {
                "task_status_counts": dict(sorted(search_reasons.items())),
                "tasks_triggered": search_tasks_triggered,
                "tasks_with_exact_programs": search_tasks_found_exact,
                "exact_programs_found": search_exact_programs,
                "partial_programs_emitted": search_partial_programs,
                "state_expansions": search_expansions,
                "elapsed_seconds": round(search_elapsed, 6),
            },
            "exact_demo_match_histogram": dict(sorted(
                match_histogram.items(), key=lambda item: int(item[0]))),
        },
        "rows": rows,
    }


def solver_digest(root: Path) -> str:
    files = sorted((root / "arc_reasoning").glob("*.py"))
    files += [root / "agents" / "arc_reasoning_agent.py"]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def evaluate_public_once(root: Path, output: Path) -> dict:
    freeze_path = root / "artifacts" / "arc_agi2" / "solver_freeze.json"
    if not freeze_path.is_file():
        raise RuntimeError("public evaluation refused: solver is not frozen")
    freeze = json.loads(freeze_path.read_text("utf-8"))
    current_digest = solver_digest(root)
    if freeze.get("solver_sha256") != current_digest:
        raise RuntimeError("public evaluation refused: frozen solver hash changed")
    if output.exists():
        raise RuntimeError(f"public evaluation refused: one-shot result already exists: {output}")
    data_root = root / "data" / "arc_agi2" / "public_evaluation"
    manifest = json.loads((data_root / "manifest.json").read_text("utf-8"))
    if manifest.get("count") != 120:
        raise RuntimeError(f"public evaluation refused: expected 120 tasks, got {manifest.get('count')}")
    solver = ArcSolver()
    rows = []
    categories: Counter[str] = Counter()
    for source_row in manifest["tasks"]:
        path = data_root / source_row["file"]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source_row["sha256"]:
            raise ValueError(f"public task changed after freeze: {source_row['file']}")
        task = json.loads(raw)
        score = score_task(solver, task)
        solved = score["pass2_outputs"] == score["output_count"]
        if not score["output_count"]:
            category = "invalid_no_test_pairs"
        elif solved:
            category = "solved"
        elif score["empty_candidates"] == score["output_count"]:
            category = "no_verified_rule"
        elif score["shape_errors"]:
            category = "output_shape"
        elif score["unexpected_color_cells"]:
            category = "unexpected_color"
        else:
            category = "wrong_cells_or_rule"
        categories[category] += 1
        rows.append({"task_id": Path(source_row["file"]).stem,
                     "task_sha256": digest, "solved_pass2": solved,
                     "category": category,
                     "top1_outputs": score["top1_outputs"],
                     "pass2_outputs": score["pass2_outputs"],
                     "output_count": score["output_count"]})
    solved_tasks = sum(row["solved_pass2"] for row in rows)
    report = {
        "benchmark": "ARC-AGI-2 official public evaluation",
        "source_commit": manifest["source_commit"],
        "task_count": len(rows), "solved_tasks": solved_tasks,
        "failed_tasks": len(rows) - solved_tasks,
        "task_accuracy": solved_tasks / len(rows) if rows else 0.0,
        "top1_test_outputs": sum(row["top1_outputs"] for row in rows),
        "pass2_test_outputs": sum(row["pass2_outputs"] for row in rows),
        "test_output_count": sum(row["output_count"] for row in rows),
        "failure_categories": dict(sorted(categories.items())),
        "solver_sha256": current_digest,
        "one_shot": True,
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--split", choices=["training_tasks", "validation_tasks"],
                        default="validation_tasks")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", default="internal_split_manifest.json",
                        help="split manifest under data/arc_agi2 or an absolute path")
    parser.add_argument("--limit", type=int,
                        help="score only the first N tasks; diagnostic subset, not a fresh holdout")
    parser.add_argument("--public-once", action="store_true")
    args = parser.parse_args()
    if args.public_once:
        if not args.output:
            parser.error("--public-once requires --output")
        report = evaluate_public_once(args.root, args.output)
    else:
        report = evaluate_internal(args.root, args.split, args.manifest, args.limit)
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
