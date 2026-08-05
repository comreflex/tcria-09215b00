# Chain-of-Custody Flow

## Overview

Every piece of information flowing through Precision Gate is:
1. **Hashed** at ingestion (SHA-256)
2. **Logged** at every product boundary
3. **Immutable** — no product modifies upstream data
4. **Auditable** — the AuditTrail records every step

## Custody Flow Diagram

```
┌──────────────────────────────────────────┐
│              TCRIA Engine                │
│  - Scans evidence files                  │
│  - Applies governance gates              │
│  - Produces audit bundle (JSON)          │
│  - Hash: SHA-256 of raw bundle           │
└──────────────────┬───────────────────────┘
                   │
       Bundle SHA-256 logged by TCRIAAdapter
                   │
┌──────────────────▼───────────────────────┐
│           TCRIAAdapter (v1.0)            │
│  - Validates bundle structure            │
│  - Non-abandonment check                 │
│  - Maps files → evidence[]               │
│  - Maps gate statuses → gate_results[]   │
│  - Hash: SHA-256 of output payload       │
└──────────────────┬───────────────────────┘
                   │
     Payload SHA-256 logged in _precision_gate_meta
                   │
┌──────────────────▼───────────────────────┐
│   TCRIAExecutionContextAdapter (Quinta   │
│   Ordem internal adapter v1.0)           │
│  - Converts payload → ExecutionContext   │
│  - Deep copy, no mutation                │
└──────────────────┬───────────────────────┘
                   │
┌──────────────────▼───────────────────────┐
│          QuintaOrdemGate.evaluate()      │
│  - 5 independent verifiers               │
│  - Returns GateDecision (frozen)         │
│  - Logs execution_context_sha256         │
└──────────────────┬───────────────────────┘
                   │
     Decision SHA-256 logged by QuintaOrdemAdapter
                   │
┌──────────────────▼───────────────────────┐
│       QuintaOrdemAdapter (v1.0)          │
│  - Converts GateDecision → custody state │
│  - Merges TCRIA non-abandonment flags    │
└──────────────────┬───────────────────────┘
                   │
┌──────────────────▼───────────────────────┐
│        CustodyStateMachine               │
│  - Enforces non-abandonment rules        │
│  - Builds immutable CustodyRecord        │
│  - All hashes preserved                  │
└──────────────────┬───────────────────────┘
                   │
┌──────────────────▼───────────────────────┐
│           AuditTrail                     │
│  - Append-only log of all events         │
│  - Each event timestamped + typed        │
│  - Serializable to JSON                  │
└──────────────────┬───────────────────────┘
                   │
┌──────────────────▼───────────────────────┐
│           ReportBuilder                  │
│  - JSON report (machine-auditable)       │
│  - Markdown summary (human-readable)     │
│  - Includes full audit trail             │
└──────────────────────────────────────────┘
```

## Custody Invariants

| Invariant | Enforced By |
|-----------|------------|
| TCRIA block cannot be overridden | `CustodyStateMachine._map_status()` |
| Input bundles never mutated | `deepcopy()` in all adapters |
| All transitions logged | `AuditTrail.append()` |
| All hashes recorded | `TCRIAAdapter`, `QuintaOrdemAdapter` |
| Audit trail is append-only | `AuditTrail` class design |
| CustodyRecord is immutable | `@dataclass(frozen=True)` |
