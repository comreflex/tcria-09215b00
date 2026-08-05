# Precision Gate Core — Mobile Custody Orchestration

Precision Gate Core is the orchestration layer that composes **TCRIA** and **Quinta Ordem Gate** while preserving chain-of-custody across both products.

## Quick Start

```bash
cd products/precision-gate-core
pip install -e .[dev]

# Install quinta-ordem-gate for full pipeline
pip install -e ../quinta-ordem-gate

# Run integration tests
pytest ../../tests/integration/ -q
```

## Pipeline Flow

```
TCRIA Bundle
    │
    ▼ TCRIAAdapter (v1.0)
Quinta Ordem Payload
    │
    ▼ TCRIAExecutionContextAdapter (quinta-ordem internal)
ExecutionContext
    │
    ▼ QuintaOrdemGate.evaluate()
GateDecision
    │
    ▼ QuintaOrdemAdapter (v1.0)
Custody State
    │
    ▼ CustodyStateMachine
CustodyRecord + AuditTrail
    │
    ▼ ReportBuilder
Custody Report (JSON + Markdown)
```

## Modules

| Module | Responsibility |
|--------|---------------|
| `precision_gate/adapters/tcria_adapter.py` | TCRIA bundle → Quinta Ordem payload |
| `precision_gate/adapters/quinta_ordem_adapter.py` | GateDecision → custody state |
| `precision_gate/adapters/api_output_adapter.py` | External API output → decision record |
| `precision_gate/custody/models.py` | `CustodyRecord`, `CustodyStatus` |
| `precision_gate/custody/state_machine.py` | Non-abandonment enforcement |
| `precision_gate/custody/audit_trail.py` | Append-only event log |
| `precision_gate/composition/pipeline.py` | Full pipeline orchestration |
| `precision_gate/reporting/report_builder.py` | JSON + Markdown reports |

## Non-Abandonment Enforcement

```python
# If TCRIA blocked, human review is ALWAYS required
if tcria_non_abandonment_flags:
    human_review = True  # Cannot be overridden

# TCRIA block overrides quinta-ordem approval
if non_abandonment_flags and base == CustodyStatus.APPROVED:
    return CustodyStatus.HUMAN_REVIEW
```

See [CUSTODY_CHARTER.md](../../CUSTODY_CHARTER.md) for full rules.

## Usage Example

```python
from precision_gate.composition.pipeline import PrecisionGatePipeline

pipeline = PrecisionGatePipeline.default()
record, trail = pipeline.run(
    tcria_bundle=bundle,
    case_id="case-001",
)

print(f"Status: {record.status.value}")
print(f"Confidence: {record.confidence:.4f}")
print(f"Human Review Required: {record.human_review_required}")
print(f"Audit Trail Events: {len(trail.entries)}")
```

## Tests

Integration tests are in `../../tests/integration/`:

```bash
pytest ../../tests/integration/ -q
```
