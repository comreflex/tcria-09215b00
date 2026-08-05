# Composition Model

## Data Flow

```
Input: TCRIA Audit Bundle
       │
       ▼
┌─────────────────────┐
│   TCRIAAdapter      │  • Validates bundle structure
│   (version 1.0)     │  • Logs input SHA-256
│                     │  • Checks non-abandonment flags
│                     │  • Produces Quinta Ordem payload
└─────────┬───────────┘
          │ quinta_ordem_adapter_version = "1.0"
          ▼
┌─────────────────────┐
│TCRIAExecutionContext │  • Converts payload → ExecutionContext
│    Adapter          │  • No filesystem access
│ (quinta_ordem pkg)  │  • Deep copy, no mutation
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  QuintaOrdemGate    │  • Evaluates 5 verification dimensions
│  .evaluate()        │  • Returns GateDecision (immutable)
│                     │  • Calculates confidence breakdown
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  QuintaOrdemAdapter │  • Converts GateDecision → custody state
│   (version 1.0)     │  • Merges TCRIA non-abandonment flags
│                     │  • Logs decision SHA-256
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ CustodyStateMachine │  • Enforces non-abandonment rules
│  .build_record()    │  • Maps status to CustodyStatus
│                     │  • Sets human_review if required
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   ReportBuilder     │  • Generates JSON + Markdown report
│   .build()          │  • Includes full audit trail
│                     │  • All hashes preserved
└─────────────────────┘
          │
          ▼
Output: CustodyRecord + AuditTrail + Report
```

## Product Boundaries

| Boundary | Mechanism |
|----------|-----------|
| TCRIA → Quinta Ordem | `TCRIAAdapter.to_execution_context_payload()` |
| Quinta Ordem → Precision Gate | `QuintaOrdemAdapter.to_custody_state()` |
| Precision Gate → Report | `ReportBuilder.build()` |

Each boundary is:
1. **Versioned** — schema version is declared in every payload
2. **Logged** — input and output SHA-256 hashes recorded
3. **Immutable** — deep copies prevent mutation of upstream data

## Adapter Contract Versions

| Contract | File |
|----------|------|
| TCRIA Bundle v1.0 | `shared/contracts/tcria_bundle_v1.0.json` |
| Quinta Ordem v1.0 | `shared/contracts/quinta_ordem_v1.0.json` |
| Precision Gate Manifest v1.0 | `shared/contracts/precision_gate_manifest.json` |
