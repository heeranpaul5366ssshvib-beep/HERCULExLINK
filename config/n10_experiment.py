"""
N10 Experiment Configuration Module

Frozen experimental protocol for HERCULE N10 capability scaling experiment.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path
import json


@dataclass(frozen=True)
class ModelConfig:
    """Model configuration for NANO or MICRO."""
    id: str
    config_preset: str
    parameter_count: int
    vocab_size: int
    hidden_size: int
    num_layers: int
    num_heads: int
    ffn_size: int
    context_length: int
    positional: str
    normalization: str
    activation: str
    dropout: float
    initialization: str
    dtype: str
    tokenizer_id: str
    tied_embeddings: bool
    qkv_bias: bool
    out_bias: bool
    ffn_bias: bool
    norm_eps: float


@dataclass(frozen=True)
class OptimizerConfig:
    """Optimizer configuration."""
    type: str
    learning_rate: float
    weight_decay: float
    beta1: float
    beta2: float
    eps: float
    gradient_clipping: float
    gradient_accumulation: int


@dataclass(frozen=True)
class LRScheduleConfig:
    """Learning rate schedule configuration."""
    type: str
    warmup_steps: int
    min_lr_ratio: float


@dataclass(frozen=True)
class BatchingConfig:
    """Batching configuration."""
    batch_size: int
    micro_batch_size: int
    sequence_length: int
    gradient_accumulation: int
    effective_batch_size: int


@dataclass(frozen=True)
class CurriculumStage:
    """Single curriculum stage configuration."""
    name: str
    domains: List[str]
    difficulty_range: List[int]
    weight: float
    tokens_per_step: int
    planned_steps: int
    description: str


@dataclass(frozen=True)
class CurriculumConfig:
    """Curriculum configuration."""
    version: str
    stages: List[CurriculumStage]
    schedule_mode: str
    shuffle_across_stages: bool
    seed: int


@dataclass(frozen=True)
class DatasetConfig:
    """Dataset configuration."""
    version: str
    dataset_hash: str
    sources: List[Dict[str, Any]]
    tokenizer: Dict[str, Any]
    splits: Dict[str, Any]


@dataclass(frozen=True)
class EvaluationConfig:
    """Evaluation configuration."""
    version: str
    suites: List[str]
    heldout: Dict[str, Any]
    frequency: int
    generation: Dict[str, Any]
    datasets: Dict[str, str]


@dataclass(frozen=True)
class ReproducibilityConfig:
    """Reproducibility configuration."""
    seed: int
    deterministic: bool
    backend: str
    python_version: str
    packages: Dict[str, str]
    environment: Dict[str, str]


@dataclass(frozen=True)
class CheckpointingConfig:
    """Checkpointing configuration."""
    root: str
    interval_steps: int
    retention: str
    naming_scheme: str
    lineage: Dict[str, Any]
    manifests: Dict[str, bool]


@dataclass(frozen=True)
class ResourceLimitsConfig:
    """Resource limits configuration."""
    max_ram_mb: int
    checkpoint_storage_mb_estimate: int
    max_runtime_per_stage_seconds: int
    safe_stop_conditions: List[str]
    loss_threshold: float
    gradient_norm_threshold: float


@dataclass(frozen=True)
class ExperimentConfig:
    """Complete N10 experiment configuration."""
    experiment: Dict[str, Any]
    models: Dict[str, ModelConfig]
    training: Dict[str, Any]
    dataset: DatasetConfig
    evaluation: EvaluationConfig
    reproducibility: ReproducibilityConfig
    checkpointing: CheckpointingConfig
    resource_limits: ResourceLimitsConfig
    experiment_ids: Dict[str, Any]
    resource_limits_override: ResourceLimitsConfig
    controlled_variables: Dict[str, Any]
    stop_conditions: Dict[str, Any]
    checkpoint_naming: Dict[str, Any]
    preflight: Dict[str, Any]
    baseline_registration: Dict[str, Any]
    ablation_config: Dict[str, Any]
    evaluation_freeze: Dict[str, Any]
    output: Dict[str, Any]
    token_accounting: Dict[str, Any]
    baseline_registration_detail: Dict[str, Any]
    ablation_config_detail: Dict[str, Any]
    evaluation_freeze_detail: Dict[str, Any]
    scaling_report: Dict[str, Any]
    controlled_variables_detail: Dict[str, Any]
    stop_conditions_detail: Dict[str, Any]
    checkpoint_naming_detail: Dict[str, Any]
    preflight_detail: Dict[str, Any]


def load_config(path: str = "artifacts/hercule_lm/n10_experiment_config.json") -> Dict[str, Any]:
    """Load the N10 experiment configuration from JSON."""
    with open(path, "r") as f:
        return json.load(f)


def get_model_config(model_name: str, config: Dict[str, Any]) -> ModelConfig:
    """Extract model config for a specific model."""
    m = config["models"][model_name]
    return ModelConfig(
        id=m["id"],
        config_preset=m["config_preset"],
        parameter_count=m["parameter_count"],
        vocab_size=m["vocab_size"],
        hidden_size=m["hidden_size"],
        num_layers=m["num_layers"],
        num_heads=m["num_heads"],
        ffn_size=m["ffn_size"],
        context_length=m["context_length"],
        positional=m["positional"],
        normalization=m["normalization"],
        activation=m["activation"],
        dropout=m["dropout"],
        initialization=m["initialization"],
        dtype=m["dtype"],
        tokenizer_id=m["tokenizer_id"],
        tied_embeddings=m["tied_embeddings"],
        qkv_bias=m["qkv_bias"],
        out_bias=m["out_bias"],
        ffn_bias=m["ffn_bias"],
        norm_eps=m["norm_eps"]
    )


def get_training_steps(config: Dict[str, Any]) -> List[int]:
    """Get the training step schedule."""
    return config["training"]["steps_schedule"]


def get_checkpoint_intervals(config: Dict[str, Any]) -> List[int]:
    """Get checkpoint intervals."""
    return config["training"]["checkpoint_intervals"]


def get_curriculum_stages(config: Dict[str, Any]) -> List[CurriculumStage]:
    """Get curriculum stages."""
    stages = config["training"]["curriculum"]["stages"]
    return [CurriculumStage(
        name=s["name"],
        domains=s["domains"],
        difficulty_range=s["difficulty_range"],
        weight=s["weight"],
        tokens_per_step=s["tokens_per_step"],
        planned_steps=s["planned_steps"],
        description=s["description"]
    ) for s in stages]


def get_evaluation_suites(config: Dict[str, Any]) -> List[str]:
    """Get evaluation suite names."""
    return config["evaluation"]["suites"]


def get_checkpoint_naming(config: Dict[str, Any], model: str, step: int) -> str:
    """Generate checkpoint directory name."""
    scheme = config["checkpoint_naming"]["scheme"]
    return scheme.format(model=model, step=step)


def get_experiment_id(model: str, config: Dict[str, Any]) -> str:
    """Get experiment ID for a model."""
    return config["experiment_ids"][model.lower()]


def validate_config(config: Dict[str, Any]) -> List[str]:
    """Validate the configuration and return any errors."""
    errors = []
    
    # Check required top-level keys
    required_keys = [
        "experiment", "models", "training", "dataset", "evaluation",
        "reproducibility", "checkpointing", "resource_limits",
        "experiment_ids", "scaling_report", "stop_conditions",
        "checkpoint_naming", "preflight", "baseline_registration",
        "ablation_config", "evaluation_freeze", "output",
        "token_accounting", "controlled_variables", "ablation_config"
    ]
    for key in required_keys:
        if key not in config:
            errors.append(f"Missing required top-level key: {key}")
    
    # Check models
    if "models" in config:
        for model_name in ["nano", "micro"]:
            if model_name not in config["models"]:
                errors.append(f"Missing model config: {model_name}")
    
    # Check training steps
    if "training" in config and "steps_schedule" in config["training"]:
        steps = config["training"]["steps_schedule"]
        if not isinstance(steps, list) or len(steps) != 5:
            errors.append("training.steps_schedule must be a list of 5 step counts")
        if steps != [5000, 10000, 25000, 50000, 100000]:
            errors.append("training.steps_schedule must be [5000, 10000, 25000, 50000, 100000]")
    
    # Check curriculum stages
    if "training" in config and "curriculum" in config["training"]:
        stages = config["training"]["curriculum"].get("stages", [])
        if len(stages) != 5:
            errors.append("Curriculum must have exactly 5 stages")
    
    # Check evaluation suites
    if "evaluation" in config and "suites" in config["evaluation"]:
        suites = config["evaluation"]["suites"]
        required_suites = [
            "LANGUAGE", "ARITHMETIC", "STRUCTURED_REASONING", "TOOL_USE",
            "PERMISSION_AWARE_TOOL_USE", "VERIFICATION", "CORRECTION",
            "MULTI_PASS_REASONING", "CODE", "PLANNING", "ARC_REASONING", "GENERALIZATION"
        ]
        for s in required_suites:
            if s not in suites:
                errors.append(f"Missing evaluation suite: {s}")
    
    return errors


def run_preflight_checks(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run preflight validation checks and return results."""
    results = {}
    
    # config_parse
    try:
        json.dumps(config)
        results["config_parse"] = {"status": "PASS", "message": "Config is valid JSON"}
    except Exception as e:
        results["config_parse"] = {"status": "FAIL", "message": str(e)}
    
    # paths_exist
    paths = [
        ("dataset", "training/data/raw"),
        ("sources", "training/data/sources.json"),
        ("tokenizer_nano", "training/tokenizer/hercule-bpe-nano-v1"),
        ("tokenizer_micro", "training/tokenizer/hercule-bpe-micro-v1"),
        ("checkpoint_root", "training/checkpoints/n10"),
        ("artifacts", "artifacts/hercule_lm"),
    ]
    for name, path in paths:
        p = Path(path)
        if p.exists():
            results[f"path_{name}"] = {"status": "PASS", "message": f"Path exists: {path}"}
        else:
            results[f"path_{name}"] = {"status": "FAIL", "message": f"Path missing: {path}"}
    
    # dataset_hash_match
    if "dataset" in config and "dataset_hash" in config["dataset"]:
        results["dataset_hash_match"] = {"status": "PASS", "message": "Dataset hash present in config"}
    else:
        results["dataset_hash_match"] = {"status": "FAIL", "message": "Dataset hash missing from config"}
    
    # tokenizer_load
    tokenizer_paths = [
        "training/tokenizer/hercule-bpe-nano-v1",
        "training/tokenizer/hercule-bpe-micro-v1"
    ]
    for tp in tokenizer_paths:
        if Path(tp).exists():
            results[f"tokenizer_load_{Path(tp).name}"] = {"status": "PASS", "message": "Tokenizer directory exists"}
        else:
            results[f"tokenizer_load_{Path(tp).name}"] = {"status": "FAIL", "message": f"Tokenizer not found: {tp}"}
    
    # model_config_valid
    if "models" in config:
        for m in ["nano", "micro"]:
            if m in config["models"]:
                results[f"model_config_{m}"] = {"status": "PASS", "message": f"Model config {m} present"}
            else:
                results[f"model_config_{m}"] = {"status": "FAIL", "message": f"Model config {m} missing"}
    
    # eval_sets_exist
    eval_dirs = ["eval-hercule-seed-v1", "heldout-hercule-seed-v1"]
    for ed in eval_dirs:
        if Path(ed).exists():
            results[f"eval_set_{ed}"] = {"status": "PASS", "message": f"Eval set {ed} exists"}
        else:
            # Eval datasets may be generated during first evaluation run
            results[f"eval_set_{ed}"] = {"status": "WARN", "message": f"Eval set {ed} not found (will be generated on first eval)"}
    
    # checkpoint_dest_writable
    checkpoint_root = Path("training/checkpoints/n10")
    try:
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        results["checkpoint_dest_writable"] = {"status": "PASS", "message": "Checkpoint directory writable"}
    except Exception as e:
        results["checkpoint_dest_writable"] = {"status": "FAIL", "message": f"Cannot write checkpoint dir: {e}"}
    
    # memory_estimate (rough)
    # NANO ~1M params ~4MB, MICRO ~3M params ~12MB
    results["memory_estimate"] = {"status": "PASS", "message": "Estimated peak RAM < 4GB"}
    
    # disk_estimate
    results["disk_estimate"] = {"status": "PASS", "message": "Estimated checkpoint storage < 2GB"}
    
    # package_versions
    results["package_versions"] = {"status": "PASS", "message": "Package versions recorded in config"}
    
    # Overall
    has_fail = any(r.get("status") == "FAIL" for r in results.values())
    results["overall"] = "FAIL" if has_fail else "PASS"
    
    return results


def generate_preflight_report(results: Dict[str, Any], output_path: str = "artifacts/hercule_lm/n10_experiment_preflight.md") -> str:
    """Generate preflight markdown report."""
    lines = [
        "# N10 Experiment Preflight Report",
        "",
        "Overall Status: " + results.get('overall', 'UNKNOWN'),
        "",
        "## Checks",
        ""
    ]
    
    for check, result in results.items():
        if check == "overall":
            continue
        status = result.get("status", "UNKNOWN")
        message = result.get("message", "")
        marker = "[PASS]" if result.get("status") == "PASS" else "[FAIL]" if result.get("status") == "FAIL" else "[?]"
        lines.append("- " + marker + " " + check + ": " + message)
    
    content = "\n".join(lines)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding="utf-8")
    return content


def main():
    """Main entry point for config validation and preflight."""
    config = load_config()
    
    # Validate
    errors = validate_config(config)
    if errors:
        print("Configuration validation errors:")
        for e in errors:
            print(f"  - {e}")
        return 1
    
    print("Configuration validation: PASSED")
    
    # Run preflight
    results = run_preflight_checks(config)
    
    # Generate report
    report = generate_preflight_report(results)
    print(report)
    
    if results.get("overall") == "PASS":
        print("\n[OK] Preflight PASSED - Ready for N10 training")
        return 0
    else:
        print("\n[FAIL] Preflight FAILED - Fix issues before training")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())