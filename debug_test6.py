from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver

task = {
    "train": [
        {"input": [[1, 0, 0]], "output": [[0, 1, 0]]},
        {"input": [[0, 2, 0]], "output": [[0, 0, 2]]},
    ],
    "test": [{"input": [[3, 0, 0]]}],
}
result = ArcSolver(advisory_ranker=lambda rows: ["identity"]).solve(task, include_coverage=True)
print("verified_rules:", result["verified_rules"])
print("candidates:", result["candidates"])
print("coverage status:", result["hypothesis_coverage"]["status"])
print("exact_training_hypotheses:", result["hypothesis_coverage"]["exact_training_hypotheses"])
print("invariance_surviving_hypotheses:", result["hypothesis_coverage"]["invariance_surviving_hypotheses"])