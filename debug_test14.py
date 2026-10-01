from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver

# Test palette role task
task = {"train": [
    {"input": [[0, 1, 2]], "output": [[0, 1, 0]]},
    {"input": [[0, 3, 4]], "output": [[0, 3, 0]]},
], "test": [{"input": [[0, 5, 6]]}]}
result = ArcSolver().solve(task, include_coverage=True)
print("verified_rules:", result["verified_rules"])
print("candidates:", result["candidates"])
coverage = result["hypothesis_coverage"]
print("exact_training_hypotheses:", coverage["exact_training_hypotheses"])
print("invariance_surviving_hypotheses:", coverage["invariance_surviving_hypotheses"])
print("exact_rule_taxonomy:", coverage["exact_rule_taxonomy"])
print("invariance_surviving_rule_taxonomy:", coverage["invariance_surviving_rule_taxonomy"])
print("invariance_check_outcomes:", coverage["invariance_check_outcomes"])