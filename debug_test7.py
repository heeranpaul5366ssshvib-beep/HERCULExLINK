from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver

task = {
    "train": [
        {"input": [[1, 0, 0]], "output": [[0, 1, 0]]},
        {"input": [[0, 2, 0]], "output": [[0, 0, 2]]},
    ],
    "test": [{"input": [[3, 0, 0]]}],
}
result = ArcSolver(advisory_ranker=lambda rows: ["identity"]).solve(task)
print("verified_rules:", result["verified_rules"])
print("candidates:", result["candidates"])
if result["candidates"][0]:
    for c in result["candidates"][0]:
        print(f"  candidate: rule={c.rule}, grid={c.grid}")