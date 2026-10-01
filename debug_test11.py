from arc_reasoning.grid import parse_grid
from arc_reasoning.primitives import connect_aligned_objects, extract_objects, infer_background

source2 = parse_grid([[2, 0, 2]])
print(f"Background: {infer_background(source2)}")
objects = extract_objects(source2, background_color=infer_background(source2))
print(f"Objects: {len(objects)}")
for i, obj in enumerate(objects):
    print(f"  Object {i}: color={obj.color}, cells={obj.cells}, bbox={obj.bbox}")

out2 = connect_aligned_objects(source2, "same")
print(f"Output: {out2}")