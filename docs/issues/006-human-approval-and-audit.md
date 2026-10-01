# Issue 006 — Human Approval UI & Audit Trails

Priority: Medium
Estimate: 1–3 person-weeks

Goal
- Provide human-in-the-loop approval endpoints and persistent audit trails for important actions.

Acceptance criteria
- API endpoints or CLI hooks to request approval and record decisions.
- Audit log storage (append-only) with sufficient metadata for investigation.

Files to change (suggested)
- `orchestrator/` — add approval workflow hooks
- `security/` — add audit log utilities
