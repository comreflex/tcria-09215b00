# Custody Charter — Non-Abandonment Principles

**Effective Date:** 2026-08-05  
**Scope:** All three Precision Gate products (TCRIA, Quinta Ordem Gate, Precision Gate Core)

---

## Core Commitment

> **No TCRIA principle may be abandoned, weakened, replaced, or silently bypassed without explicit owner consent.**

This charter is enforced in code, not only in documentation.

---

## Non-Abandonment Rules

### Rule 1: TCRIA Prescriptive Gate Blocks Are Preserved

If TCRIA's prescriptive gate returns `blocked`, the Precision Gate pipeline **must**:
- Set `human_review_required = True` on the custody record.
- Record the block in `non_abandonment_flags`.
- Never allow a Quinta Ordem `approved` decision to override the block.

**Implementation:** `CustodyStateMachine._map_status()` enforces this invariant.

### Rule 2: Immutable Snapshots

Original TCRIA bundles and Quinta Ordem decisions are **never mutated**. Adapters work on deep copies only.

**Implementation:** All adapters use `copy.deepcopy()` before any transformation.

### Rule 3: SHA-256 Hash Trail

Every product transition records SHA-256 hashes of:
- Input bundle (TCRIA → Precision Gate)
- Output payload (Precision Gate → Quinta Ordem)
- Gate decision (Quinta Ordem → Precision Gate)

**Implementation:** `TCRIAAdapter`, `QuintaOrdemAdapter`, and `AuditTrail` all log hashes.

### Rule 4: Audit Trail Is Append-Only

The `AuditTrail` class never removes or edits entries. It is append-only and can be persisted as a human-readable JSON file.

### Rule 5: Human Review Gates

Any of the following conditions **must** trigger `human_review_required = True`:
- Quinta Ordem status is not `approved`
- TCRIA non-abandonment flags are present
- Confidence score is below approval threshold (0.95)

---

## Enforcement in Code

```python
# CustodyStateMachine.build_record() — non-abandonment enforcement
if tcria_non_abandonment_flags:
    human_review = True  # Cannot be overridden

# _map_status() — TCRIA block overrides quinta-ordem approval
if non_abandonment_flags and base == CustodyStatus.APPROVED:
    return CustodyStatus.HUMAN_REVIEW
```

---

## Violation Protocol

If a code change would weaken or bypass any rule above:
1. It must be explicitly approved by the product owner.
2. The approval must be documented in a commit message with `CUSTODY_CHARTER_EXCEPTION:`.
3. Integration tests must still pass — no test may be deleted to enable a bypass.

---

## Versioning

This charter is versioned with the repository. Changes require:
- Explicit owner sign-off
- Update to this document
- Update to integration tests in `tests/integration/test_custody_preservation.py`
