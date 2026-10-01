import time
from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver

# Simple test task
task = {"train": [
    {"input": [[1, 0, 0]], "output": [[0, 1, 0]]},
    {"input": [[0, 2, 0]], "output": [[0, 0, 2]]},
], "test": [{"input": [[3, 0, 0]]}]}

solver = ArcSolver()
start = time.time()
result = solver.solve(task, include_coverage=True)
elapsed = time.time() - start
print(f"Elapsed: {elapsed:.3f}s")
print(f"Verified rules: {result['verified_rules']}")
print(f"Candidates: {len(result['candidates'][0])}")
print(f"Coverage status: {result['hypothesis_coverage']['status']}")
print(f"Generated hypotheses: {result['hypothesis_coverage']['generated_hypotheses']}")