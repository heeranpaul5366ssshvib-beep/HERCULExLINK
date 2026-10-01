from arc_reasoning.grid import parse_grid
from arc_reasoning.rules import generate_hypotheses
from arc_reasoning.solver import verify_rule
from arc_reasoning.invariance import check_rule_invariance

pairs = ((parse_grid([[1, 0, 0, 1]]), parse_grid([[1, 1, 1, 1]])),
         (parse_grid([[2, 0, 2]]), parse_grid([[2, 2, 2]])))
rules = generate_hypotheses(pairs)
for rule in rules:
    valid, matched = verify_rule(rule, pairs)
    if valid:
        print(f'EXACT: {rule.name}: family={rule.family}, local_writes={rule.local_writes}, relation_predicates={rule.relation_predicates}')
        report = check_rule_invariance(rule, pairs)
        print(f'  invariance: passed={report["passed"]}, failed={report["failed"]}, accepted={report["accepted"]}')
        print(f'  checks: {report["checks"]}')