from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver

task = {"train": [
    {"input": [[1, 0, 2], [5, 5, 5], [0, 2, 0]],
     "output": [[1, 2, 2]]},
    {"input": [[3, 0], [4, 4], [0, 3]],
     "output": [[3, 3]]},
], "test": [{"input": [[2, 0], [6, 6], [0, 2]]}]}
result = ArcSolver().solve(task, include_coverage=True)
print("verified_rules:", result["verified_rules"])
print("candidates:", result["candidates"])
coverage = result["hypothesis_coverage"]
print("exact_training_hypotheses:", coverage.get("exact_training_hypotheses"))
print("invariance_surviving_hypotheses:", coverage.get("invariance_surviving_hypotheses"))
print("exact_rule_taxonomy:", coverage.get("exact_rule_taxonomy"))
print("invariance_surviving_rule_taxonomy:", coverage.get("invariance_surviving_rule_taxonomy"))