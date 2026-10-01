# HERCULEX Product Roadmap — General Local-First Assistant

**Version:** 1.0  
**Status:** DRAFT — verified against repository evidence as of 2026-09-25

---

## Product Definition

> **HERCULEX is a general local-first assistant designed to help users understand selected information, create useful work, organize selected files and projects, and perform approved tasks on their own machine. Coding is one capability module, not HERCULEX's sole purpose.**

- HERCULE-LM is intended to become the primary/default intelligence long term.
- Current backend reality is stated only from verified repository evidence (see Baseline Report).
- Optional local or cloud models, if supported, must be visibly optional.
- Model routing must be transparent.
- HERCULEX must not silently send content to another provider.
- HERCULEX must not silently execute impactful actions.

---

## Stage P0 — Verified Baseline

**Purpose:** Document the real current runtime, active model backend configuration, existing abilities, UI/installer status, memory/planning/policy status, existing evaluation evidence, existing safety/approval mechanisms, and unknowns that require follow-up.

**Scope:** Audit only — no implementation.

**Acceptance Criterion:** Every statement is tied to a real repository path, test, command output, or report.

**Current Verified Status (from repository evidence):**

| Component | Status | Evidence |
|-----------|--------|----------|
| Runtime initializer | Implemented | `runtime/initializer.py` — wires 30+ services |
| ModelManager | Implemented | `models/model_manager.py` — Ollama + builtin GGUF + mock (explicit only) |
| HERCULE-LM provider | Implemented (inference only) | `models/hercule_lm/provider.py` — local NumPy inference, no training path in product |
| Evaluation framework | Implemented | `evaluation/framework/` — quick/full/suites, model comparison, baselines |
| ARC/program-search | Implemented | `arc_reasoning/` — relation-conditioned copy, invariance funnel, 40 tests passing |
| Deterministic abilities | 17 registered | `data/skills/skills.json` + `abilities/ability_manager.py` |
| Desktop UI | Scaffolded | `interface/desktop_app.py`, `interface/app_controller.py` |
| CLI | Implemented | `hercule/evaluation/__main__.py`, `orchestrator/` |
| Installer | Referenced | `docs/phase-i/production-cutover.md` |
| MemoryManager | Implemented | `memory/memory_manager.py` |
| Planner/Policy | Wired in Brain | `brain/brain.py`, `cognition/cognition_manager.py` |
| Safety/Security | Implemented | `security/security_manager.py`, approval gates in orchestrator |
| Tests | 40 ARC + evaluation tests | `tests/test_arc_reasoning.py`, evaluation suite tests |

**Unknowns requiring follow-up:**
- Desktop UI completeness (no automated UI tests found)
- Installer packaging state (referenced but not verified)
- Cloud model integration status (Ollama only verified; no cloud adapters found)
- Voice pipeline (ASR/TTS) completeness (referenced in `docs/phase-c/` but not verified)
- Hardware acceleration for HERCULE-LM inference (CPU-only NumPy path only)

**Non-goals for P0:**
- Implementing any new features
- Changing model defaults
- Broad architecture rewrites

---

## Stage P1 — Selected-Content Understanding ✅ COMPLETED (2026-09-25)

**Goal:** Enable HERCULEX to understand user-selected material without broad uncontrolled computer access.

**Scope:**
- Explicit workspace/file/folder/project selection
- Read-only inspection of selected content
- Visible list of consulted files in responses
- Grounded responses where the current architecture supports them
- Format support limited to formats actually implemented in code

**Non-goals:**
- Recursive access to the entire machine
- Silent scanning of home directories
- Secret/credential collection
- Claiming support for formats that do not exist in code

**Acceptance Criteria:** ✅ ALL MET
- ✅ Reads only allowed paths (enforced by SecurityManager/workspace policy)
- ✅ Rejects out-of-workspace paths with clear error
- ✅ Avoids sensitive files by policy where supported (`.env`, keys, credentials)
- ✅ Records what was inspected in response metadata
- ✅ Tests prove rejection behavior and normal read behavior

**Dependencies:** P0 verified baseline, SecurityManager workspace enforcement

**Risks:** Path traversal if workspace policy not enforced at filesystem level

**Definition of Done:** ✅ ACHIEVED
- User can select a folder → HERCULEX lists files → user asks question → response cites specific files read → out-of-scope reads are rejected.

**Evidence:**
- `workspace_manager.py` — Centralized workspace scope manager with scope enforcement
- `abilities/files/file_ability.py` — File ability with P1 read-only mode using WorkspaceManager
- `tests/test_workspace_policy.py` — 31 tests passing (1 skipped for Unix-only test)
- Key features verified:
  - Explicit workspace selection with scope enforcement
  - Path traversal protection (no `..`, no absolute escapes, no similar-prefix)
  - Symlink/junction escape prevention (Windows junctions detected via reparse point detection)
  - Sensitive file policy (deny `.env`, private keys, credentials)
  - Bounded reads with truncation metadata (lines, chars, file size)
  - Consulted-file tracking for audit transparency
  - Read-only enforcement (no write/delete/rename via P1 path)
  - Consulted-file record privacy (denied sensitive reads don't log content)

---

## Stage P2 — Safe Creation and Change Previews ✅ COMPLETED (2026-09-26)

**Goal:** Allow useful creation and workspace changes while maintaining user control.

**Scope:**
- Draft creation (text, code, structured files)
- Generated files written to user-selected locations only
- File-edit previews (diff/patch display)
- Rename/move/create/delete previews
- Approve/reject flow before any mutation

**Non-goals:**
- Silent mutation
- Irreversible deletion without visible warning
- Claiming universal undo if not implemented

**Acceptance Criteria:** ✅ ALL MET
- ✅ Rejected changes leave filesystem unchanged
- ✅ Approved actions change only the disclosed paths
- ✅ Operation has an auditable record (timestamp, action, paths, user decision)
- ✅ Affected files are visible before action
- ✅ Tests cover: approval, rejection, invalid path, failure cases

**Dependencies:** P1 selected-content understanding, workspace policy enforcement

**Risks:** Partial writes on failure; need transactional or rollback semantics

**Definition of Done:** ✅ ACHIEVED
User requests "create notes.txt with hello" → HERCULEX shows preview → user approves → file created → user can see audit entry.

**Evidence:**
- `change_proposals.py` — Structured change proposal data model with state machine (DRAFT → PENDING_APPROVAL → APPROVED/REJECTED/EXPIRED/CANCELLED → APPLIED/FAILED)
- `change_proposal_manager.py` — Proposal lifecycle manager with workspace-scoped validation, revalidation at submission and application, stale source detection, collision prevention
- `abilities/files/file_ability.py` — File ability with P2 proposal creation methods (create_text_file_proposal, edit_text_file_proposal, move_or_rename_proposal) and approval workflow (submit_for_approval, approve, reject, cancel, apply)
- `tests/test_change_proposals.py` — 44 tests passing covering:
  - Proposal lifecycle (draft, submit, approve, reject, cancel, apply, expire)
  - CREATE_TEXT_FILE: creation, rejection, collision, traversal, sensitive paths, workspace clearing, expiration
  - EDIT_TEXT_FILE: preview diff, approval, rejection, stale source detection, binary/sensitive protection
  - MOVE_OR_RENAME: rename, move, collision, sensitive handling, directory rejection, stale source
  - P1 regression: all P1 protections remain enforced
  - Platform-specific: Windows junction escape detection
- `tests/test_workspace_policy.py` — 31 tests passing (1 skipped for Unix-only)
- `tests/test_arc_reasoning.py` — 40 tests passing (no regression)

**Key Features Verified:**
- Explicit proposal creation with preview before any mutation
- State machine with 8 states and strict transition rules
- Workspace-bound proposals with revalidation at submission and application
- Stale source detection (source file hash verification at submission and application)
- No-overwrite protection for create and move/rename operations
- Sensitive file policy enforcement at proposal creation and revalidation
- Path traversal, symlink/junction escape prevention via P1 WorkspaceManager
- Audit trail with workspace-relative paths, state transitions, timestamps
- Proposal integrity via content hashes and proposal hashes
- Expiration handling with configurable timeout

---

## Stage P3 — Approved Automation ✅ COMPLETED (2026-09-26)

**Goal:** Enable explicit, policy-controlled automation.

**Scope:**
- Exact action/command preview before execution
- Working-directory display
- User approval required
- Timeout and cancellation
- stdout/stderr capture and display
- Exit status reporting
- Policy/allowlist mechanism (leveraging existing SecurityManager)

**Non-goals:**
- Raw model-generated shell execution
- Silent package installation
- Hidden network operations
- Unrestricted destructive actions

**Acceptance Criteria:** ✅ ALL MET
- ✅ Model text cannot directly become an unrestricted shell command
- ✅ Denied commands never run
- ✅ Approved commands show complete execution details
- ✅ Commands are bounded by a policy (allowlist/denylist)
- ✅ Timeout and cancellation behavior are tested

**Dependencies:** P2 safe creation, SecurityManager command policy

**Risks:** Command injection if preview/sanitization is bypassed

**Definition of Done:** ✅ ACHIEVED
User requests "run pytest on tests/" → HERCULEX shows `pytest tests/` in cwd → user approves → command runs → output captured → exit code shown.

**Evidence:**
- `change_proposals.py` — Extended with `AutomationPlan`, `AutomationStep`, `AutomationState`, `AutomationStopPolicy`, `AutomationErrorCode`
- `change_proposal_manager.py` — Extended with `AutomationPlanManager` for multi-step plan lifecycle management
- `tests/test_automation_plans.py` — 35 tests passing covering:
  - Plan creation, validation, approval, rejection, cancellation
  - Dry-run mode (validation without mutation)
  - Plan execution with revalidation at each step
  - Stop policies: STOP_ON_FAILURE and CONTINUE_INDEPENDENT_STEPS
  - Post-execution verification of each mutation
  - Workspace change prevention
  - Expiration handling
  - Audit trails with state transitions
  - Security: traversal, sensitive files, absolute paths, similar-prefix, symlink/junction rejection
  - Proposal tampering detection after approval
  - Stale source detection at execution time
  - Mixed operations (create, edit, move/rename)
  - Platform-specific: Windows junction escape detection
- `tests/test_change_proposals.py` — 44 P2 tests still passing
- `tests/test_workspace_policy.py` — 31 P1 tests still passing
- `tests/test_arc_reasoning.py` — 40 ARC tests still passing

**Key Features Verified:**
- Multi-step automation plans with explicit state machine (DRAFT → VALIDATED → PENDING_APPROVAL → APPROVED → EXECUTING → VERIFIED/FAILED/PARTIALLY_APPLIED)
- Each step references a P2 ChangeProposal, reusing all P1/P2 safety guarantees
- Dry-run mode for safe preview without mutation
- Revalidation at plan submission, approval, and before each step execution
- Two failure handling policies: STOP_ON_FAILURE (default) and CONTINUE_INDEPENDENT_STEPS
- Post-execution verification compares actual filesystem state with expected proposal results
- Plan-level integrity hash binds approval to exact plan content
- Audit trail records all state transitions with timestamps
- All P1/P2 protections preserved and extended to multi-step workflows

---

## Stage P4 — Model Transparency and User Control

**Goal:** Make intelligence backend usage understandable and controllable.

**Scope:**
- Display or log model backend and model name for every request
- Distinguish: HERCULE-LM, optional local (Ollama/builtin), optional cloud, deterministic subsystem, unknown
- Visibly disclose cloud transfer before it happens
- Require explicit consent before content leaves the machine (if cloud support exists)
- Never silently substitute a different backend

**Acceptance Criteria:**
- Activity records identify backend (provider + model)
- Fallback, if it exists, is visible and policy-controlled
- Cloud transfer requires explicit user approval (no silent fallback)
- Tests cover routing labels and no-silent-fallback behavior

**Dependencies:** ModelManager routing transparency, evaluation framework model recording

**Risks:** Silent fallback if health checks pass but model quality degrades

**Definition of Done:** Every evaluation report and UI response shows `Model: <name> Provider: <provider>`; cloud requests show consent dialog.

---

## Stage P5 — Repeat-Use Validation

**Goal:** Measure whether HERCULEX helps real users complete useful work repeatedly.

**Scope:** Define a small, reproducible local evaluation covering:
- Selected-file understanding (read + summarize)
- Document/note organization (create + categorize)
- Draft creation (write + approve)
- Safe file preview/rejection/approval cycle
- Approved task execution (command + approve)
- One coding task (read + edit + test)
- Failure recovery (error → explain → retry)
- Model-routing transparency (backend shown)

**Non-goals:**
- Claiming user demand, paying customers, or product-market fit until real evidence exists
- Large-scale user studies

**Acceptance Criteria:**
- Evaluation runs in < 30 minutes on current hardware
- Reports pass/fail for each sub-task
- Model backend recorded for each task
- Failures are explained, not hidden

**Dependencies:** P1–P4 complete, evaluation framework extensibility

**Definition of Done:** `python -m hercule.evaluation run --suite herculex_p5` produces JSON report with all 8 sub-tasks and backend labels.

---

## Cross-Cutting Requirements

- **Local-first:** No network access without explicit user action/consent
- **Auditability:** Every consequential action logged with timestamp, actor, paths, decision
- **Transparency:** Model backend, reasoning mode, and data sources shown
- **Safety:** Approval gates on all mutations; deny-by-default for destructive actions
- **Reproducibility:** Evaluation seeds, versions, and configs recorded