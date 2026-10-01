from arc_reasoning.grid import parse_grid
from arc_reasoning.primitives import connect_aligned_objects

# Test first pair
source1 = parse_grid([[1, 0, 0, 1]])
expected1 = parse_grid([[1, 1, 1, 1]])
out1 = connect_aligned_objects(source1, "same")
print(f"Pair 1: {out1 == expected1}, got {out1}, expected {expected1}")

# Test second pair
source2 = parse_grid([[2, 0, 2]])
expected2 = parse_grid([[2, 2, 2]])
out2 = connect_aligned_objects(source2, "same")
print(f"Pair 2: {out2 == expected2}, got {out2}, expected {expected2}")