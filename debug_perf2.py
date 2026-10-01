import time
from arc_reasoning.grid import parse_grid
from arc_reasoning.solver import ArcSolver

# Marker tracking task (triggers relation hypotheses)
task = {"train": [
    {"input": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 2, 0, 0], [0, 0, 0, 0, 0, 0, 0]],
     "output": [[1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0]]},
    {"input": [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]],
     "output": [[0, 0, 0, 0, 0, 1, 1], [0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0], [0, 1, 1, 0, 0, 0, 0]]},
], "test": [{"input": [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 2, 0],
                            [0, 0, 0, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0]]}]}

solver = ArcSolver()
start = time.time()
result = solver.solve(task, include_coverage=True)
elapsed = time.time() - start
print(f"Elapsed: {elapsed:.3f}s")
print(f"Verified rules: {result['verified_rules']}")
print(f"Candidates: {len(result['candidates'][0])}")
coverage = result['hypothesis_coverage']
print(f"Coverage status: {coverage['status']}")
print(f"Generated hypotheses: {coverage['generated_hypotheses']}")
print(f"Exact training hypotheses: {coverage['exact_training_hypotheses']}")
print(f"Invariance surviving: {coverage['invariance_surviving_hypotheses']}")