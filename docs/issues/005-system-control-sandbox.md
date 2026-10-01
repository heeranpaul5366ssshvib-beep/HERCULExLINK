# Issue 005 — System-Control Sandbox & Permission Model

Priority: High
Estimate: 1–2 person-weeks

Goal
- Harden system-control adapters with sandboxing, explicit permission checks, and audit logging.

Acceptance criteria
- System control actions require explicit roles/consent and are audited to logs.
- A sandbox mode that can simulate actions without making changes.
- Unit tests covering permission checks and sandbox behavior.

Files to change (suggested)
- `abilities/system_control/system_control_ability.py` — add permission checks
- `system/` — add sandbox utilities and audit logger
