# Model Capability System & Routing

## Capability registry (`models/capabilities.py`)

`ModelCapability` grades reasoning/coding/vision/embeddings/
structured-output/tool-calling/multimodal (0..1) plus context length,
measured latency, memory footprint, throughput, hardware, and
availability. `ModelCapabilityRegistry.matching` enforces graded
requirements + context/latency constraints, best-fit first.
`profile_from_info` bridges legacy `ModelInfo` entries (declared names
→ 0.7); measurements overwrite via `update`.

## Health (`models/model_health.py`)

`ModelHealthMonitor` probes each adapter's real `health()` and tracks
AVAILABLE / READY / LOADING / DEGRADED / UNAVAILABLE / FAILED with
latency, consecutive success/failure counters, and aware timestamps.
Single success ≠ trust (LOADING); slowness → DEGRADED; threshold
breaches → FAILED. The monitor never mutates adapters.

## Routing memory (`models/routing_performance.py`)

Per-model, per-task-type success/latency with EWMA latency and prior
smoothing (default prior 2/4): one anomaly cannot invert rankings, and
`best_model` stays silent until `min_samples` observations.

## Advanced router (`models/router/advanced_router.py`)

Wraps the existing `ModelRouter` (composition). Scores =
0.35·capability + 0.20·availability + 0.15·health + 0.10·latency +
0.10·resources + 0.10·history. Incapable or unhealthy models fail
closed. Task type comes from the existing `TaskClassifier`; explicit
`preferred_model` wins ties; resource fit uses measured psutil data
when available.

`RoutingDecision` exposes model, concise reason, per-candidate factor
scores, and the ordered fallback chain — no hidden reasoning.
`generate_with_fallback` walks the chain recording routing memory and
raises `ModelRoutingFailure(decision=…)` on total failure: a clear
failure, never a silent success.
