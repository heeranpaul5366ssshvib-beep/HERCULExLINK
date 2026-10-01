# Issue 007 — CI & Test Harness for Agent Workflows

Priority: Medium
Estimate: 1–2 person-weeks

Goal
- Add CI jobs and a test harness to validate long-running agent workflows, memory integration, and basic security checks.

Acceptance criteria
- `pytest` tests that exercise memory → model adapter → agent loop with mocks.
- CI config (GitHub Actions or similar) with lint, unit tests, and a smoke integration test.

Files to change (suggested)
- `tests/` — add integration test(s)
- `.github/workflows/ci.yml` — add CI pipeline
