# Quinta Ordem Gate — Deterministic Verification Product

Quinta Ordem Gate is an independent, deterministic quality gate for AI systems.
It evaluates an `ExecutionContext` through five verification dimensions and emits
a `GateDecision` with a structured confidence breakdown.

## Quick Start

```bash
cd products/quinta-ordem-gate
pip install -e .[dev]
pytest
```

## Core Modules

| Module | Responsibility |
|--------|---------------|
| `src/quinta_ordem/gate.py` | `QuintaOrdemGate` — main evaluation engine |
| `src/quinta_ordem/models.py` | Domain types: `ExecutionContext`, `GateDecision`, `Finding` |
| `src/quinta_ordem/confidence.py` | Confidence calculation across five dimensions |
| `src/quinta_ordem/validation.py` | Structural validation of `ExecutionContext` |
| `src/quinta_ordem/serialization.py` | Deterministic, cycle-safe JSON serialization |
| `src/quinta_ordem/verifiers/` | Five core verifier implementations |
| `src/quinta_ordem/adapters/tcria.py` | TCRIA bundle → `ExecutionContext` adapter |
| `src/quinta_ordem/reporting.py` | Human-readable custody reports |

## Decision Outcomes

| Status | Condition |
|--------|-----------|
| `approved` | Confidence ≥ 0.95, no findings |
| `conditional` | Confidence ≥ 0.95 but warnings present |
| `returned_for_correction` | Confidence ≥ 0.80 but HIGH findings present |
| `blocked` | Any CRITICAL finding |

## Standalone Usage

```python
from quinta_ordem import QuintaOrdemGate, ExecutionContext

gate = QuintaOrdemGate.default()
context = ExecutionContext(
    execution_id="case-001",
    evidence=[{"artifact_id": "doc-1", "source_path": "/abs/path/doc.pdf"}],
    artifacts=[],
    gate_results=[],
    logs=[],
    decisions=[{"decision_id": "dec-1", "promoted": False}],
    metadata={"open_points": []},
)
decision = gate.evaluate(context)
print(decision.status, decision.confidence)
```

## Adapter Contract (Inbound)

When used within Precision Gate, the `TCRIAExecutionContextAdapter` converts a
TCRIA audit bundle into an `ExecutionContext`. The adapter schema version is `"1.0"`.

See `../../shared/contracts/quinta_ordem_v1.0.json` for the full schema.

## Tests

```bash
pytest tests/ -q
```
