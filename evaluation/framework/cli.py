from __future__ import annotations
"""CLI for the evaluation subsystem (Phases 14, 15, 12, 13).

Commands:
  quick                     fast smoke evaluation (minutes)
  full                      complete evaluation (longer)
  run --suite NAME          one suite
  suites                    list registered suites
  compare --models a,b      same suites across installed local models
  baseline --save/--compare PATH   regression baseline vs recorded run

Results: human-readable report on stdout + machine-readable JSON under
the writable evaluation results dir. No official benchmark protocol is
claimed; internal tasks are labeled benchmark-style.
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

from evaluation.framework.config import EvalConfig
from evaluation.framework.registry import available_suites, registry_report, suite_tasks
from evaluation.framework.result import SuiteRun, new_run_id, results_dir, utc_now_iso
from evaluation.framework.reporting import (compare_to_baseline, format_report,
                                            load_baseline, save_baseline,
                                            save_report_json, suite_metrics)
from evaluation.framework.runner import EvaluationRunner
from evaluation.framework.suites import COMPARE_SUITES, QUICK_SUITES, resolve_suites
from evaluation.framework.task import EvalTask
from evaluation.framework.version import app_version


def _build_runner(config: EvalConfig, services: Optional[Dict[str, Any]] = None):
    from evaluation.framework.adapters import build_adapter
    adapter = build_adapter(live=config.live, model=config.model, services=services)
    runner = EvaluationRunner(adapter, config)
    # HUD/UI progress hook (Phase 17): attached only when a state object
    # was installed by the UI layer; harmless when absent.
    state = getattr(config, "progress_state", None)
    if state is not None:
        state.start_run(mode=config.mode, model=adapter.default_model(),
                        provider=adapter.default_provider())
        runner.on_task_done = state.update
    return runner


def _run_suites(runner: EvaluationRunner, suite_ids: List[str],
                services: Optional[Dict[str, Any]] = None) -> SuiteRun:
    """Run suites sequentially (ACTIVE tasks never overlap suites)."""
    all_results = []
    started_wall = 0.0
    started_at = utc_now_iso()
    for suite_id in suite_ids:
        tasks: List[EvalTask] = suite_tasks(suite_id)
        if suite_id == "multimodal" and services is not None:
            from evaluation.framework.datasets.multimodal import multimodal_tasks
            tasks = multimodal_tasks(services)
        if not tasks:
            continue
        run = runner.run_suite(tasks, scope=suite_id)
        started_wall += run.wall_ms
        all_results.extend(run.results)
    combined = SuiteRun(
        run_id=new_run_id(runner.config.mode), scope=runner.config.mode,
        results=all_results, version=app_version(),
        model=runner.adapter.default_model(), provider=runner.adapter.default_provider(),
        started_at=started_at, finished_at=utc_now_iso(), wall_ms=started_wall,
        config=runner.config.as_dict())
    from evaluation.framework.result import save_run
    save_run(combined)
    return combined


def _finish(config: EvalConfig, run: SuiteRun) -> int:
    print(format_report(run))
    json_path = save_report_json(run, results_dir() / f"report-{run.run_id}.json")
    print(f"\nJSON report: {json_path}")
    if config.baseline:
        from system.version import __version__
        path = results_dir() / f"baseline-v{__version__}.json"
        save_baseline(run, path)
        print(f"Baseline saved: {path}")
    state = getattr(config, "progress_state", None)
    if state is not None:
        state.finish_run()
    return 0 if run.counts.get("error", 0) == 0 else 0  # errors are data, not CLI failure


def cmd_quick(config: EvalConfig, services=None) -> int:
    config.mode = "quick"
    runner = _build_runner(config, services)
    run = _run_suites(runner, resolve_suites(config.suites, "quick"), services)
    return _finish(config, run)


def cmd_full(config: EvalConfig, services=None) -> int:
    config.mode = "full"
    runner = _build_runner(config, services)
    run = _run_suites(runner, resolve_suites(config.suites, "full"), services)
    return _finish(config, run)


def cmd_run(config: EvalConfig, suite: str, services=None) -> int:
    runner = _build_runner(config, services)
    tasks = suite_tasks(suite)
    if suite == "multimodal" and services is not None:
        from evaluation.framework.datasets.multimodal import multimodal_tasks
        tasks = multimodal_tasks(services)
    run = runner.run_suite(tasks, scope=suite)
    return _finish(config, run)


def cmd_suites() -> int:
    print("Registered evaluation suites (benchmark-style, internal):")
    for spec in registry_report():
        styles = ", ".join(spec["style_labels"]) or "-"
        print(f"  {spec['suite_id']:16s} {spec['category']:18s} {spec['title']}")
        print(f"{'':18s} styles: {styles}")
    return 0


def cmd_compare(config: EvalConfig, models: List[str], suites: List[str],
                services=None) -> int:
    """Same suites across installed local models (Phase 12).

    Only models actually discovered by ModelManager/Ollama are used.
    """
    runner = _build_runner(config, services)
    installed = runner.adapter.installed_models()
    if not installed:
        print("No installed local models discovered by ModelManager/Ollama; "
              "model comparison unavailable (reported honestly, nothing fabricated).")
        return 1
    requested = [m for m in models if m] or installed
    unknown = [m for m in requested if m not in installed]
    if unknown:
        print(f"Skipping models not installed: {', '.join(unknown)}")
    selected = [m for m in requested if m in installed]
    if not selected:
        print("No comparable models installed.")
        return 1
    suite_ids = suites or COMPARE_SUITES
    original_model = runner.adapter.default_model()
    comparison: List[Dict[str, Any]] = []
    for model in selected:
        try:
            runner.adapter.set_model(model)
        except Exception as exc:
            print(f"  {model}: unavailable ({exc})")
            continue
        run = _run_suites(runner, suite_ids, services)
        metrics = suite_metrics(run)
        counts = run.counts
        agentic = [r for r in run.results if r.category == "AGENTIC"]
        comparison.append({
            "model": model,
            "accuracy": metrics.get("categories", {}),
            "passed": counts.get("passed", 0), "failed": counts.get("failed", 0),
            "errors": counts.get("error", 0), "timeouts": counts.get("timeout", 0),
            "mean_ms": metrics.get("mean_ms"), "median_ms": metrics.get("median_ms"),
            "p95_ms": metrics.get("p95_ms"),
            "tool_success": (round(sum(1 for r in agentic if r.outcome.value == "passed")
                                   / len(agentic), 3) if agentic else None),
        })
    try:
        runner.adapter.set_model(original_model)
    except Exception:
        pass
    print("\nMODEL COMPARISON (HERCULE internal suites: "
          f"{', '.join(suite_ids)})")
    for row in comparison:
        print(f"  {row['model']}: passed={row['passed']} failed={row['failed']} "
              f"errors={row['errors']} timeouts={row['timeouts']} "
              f"median_ms={row['median_ms']} p95_ms={row['p95_ms']} "
              f"tool_success={row['tool_success']}")
    return 0 if comparison else 1


def cmd_baseline(config: EvalConfig, save: Optional[str], compare: Optional[str],
                 suites: List[str], services=None) -> int:
    runner = _build_runner(config, services)
    run = _run_suites(runner, suites or QUICK_SUITES, services)
    if save:
        path = save_baseline(run, save)
        print(f"Baseline saved: {path}\n")
        print(format_report(run))
        return 0
    if compare:
        baseline = load_baseline(compare)
        verdict = compare_to_baseline(run, baseline)
        print(format_report(run))
        print("\nREGRESSION COMPARISON")
        print(f"  baseline: {verdict['baseline_run_id']} (v{verdict['baseline_version']})")
        print(f"  current : {verdict['current_run_id']} (v{verdict['current_version']})")
        for category, entry in verdict["categories"].items():
            print(f"  {category:18s} accuracy {entry['accuracy_baseline']} -> "
                  f"{entry['accuracy_now']}  (delta {entry['accuracy_delta']})")
        for regression in verdict["regressions"]:
            print(f"  REGRESSION: {regression}")
        print(f"  verdict: {verdict['verdict']}")
        return 0
    print("baseline requires --save PATH or --compare PATH")
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m hercule.evaluation",
        description="HERCULE internal evaluation & benchmarking (quick/full suites, "
                    "model comparison, regression baselines). Internal benchmark-style "
                    "tasks only; no official benchmark protocol is claimed.")
    parser.add_argument("command", nargs="?", default="quick",
                        choices=["quick", "full", "run", "suites", "compare",
                                 "baseline", "help"])
    parser.add_argument("--suite", action="append", dest="suites", default=[],
                        help="suite id (repeatable; default: mode-appropriate set)")
    parser.add_argument("--model", default=None, help="default model override")
    parser.add_argument("--timeout", type=float, default=None,
                        help="per-task timeout seconds")
    parser.add_argument("--max-tasks", type=int, default=None,
                        help="cap tasks per suite (0 = all)")
    parser.add_argument("--parallel", type=int, default=1,
                        help="task parallelism for READ_ONLY tasks (ACTIVE always serial)")
    parser.add_argument("--models", default="", help="comma list for compare")
    parser.add_argument("--save", default=None, help="baseline save path")
    parser.add_argument("--path", default=None, help="baseline compare path")
    parser.add_argument("--baseline", action="store_true",
                        help="record run as version baseline")
    args = parser.parse_args(argv)

    if args.command in ("help",):
        parser.print_help()
        return 0
    if args.command == "suites":
        return cmd_suites()

    config = EvalConfig.from_env().sanitized()
    if args.suites:
        config.suites = list(args.suites)
    if args.model:
        config.model = args.model
    if args.timeout is not None:
        config.timeout_s = args.timeout
    if args.max_tasks is not None:
        config.max_tasks = args.max_tasks
    if args.parallel:
        config.parallel = args.parallel
    if args.baseline:
        config.baseline = True
    config = config.sanitized()

    services = None
    if config.live:
        try:
            from runtime.initializer import RuntimeInitializer
            services = RuntimeInitializer().initialize()
        except Exception as exc:
            print(f"Live runtime unavailable ({exc}); rerun with HERCULE_EVAL_LIVE=0 "
                  "for the hermetic pipeline.")
            return 1

    if args.command == "quick":
        return cmd_quick(config, services)
    if args.command == "full":
        return cmd_full(config, services)
    if args.command == "run":
        if not args.suites:
            print("run requires --suite NAME")
            return 2
        exit_code = 0
        for suite in args.suites:
            exit_code = cmd_run(config, suite, services)
        return exit_code
    if args.command == "compare":
        return cmd_compare(config, [m.strip() for m in args.models.split(",") if m.strip()],
                           args.suites, services)
    if args.command == "baseline":
        return cmd_baseline(config, args.save, args.path, args.suites, services)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
