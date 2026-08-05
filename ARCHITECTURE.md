# Precision Gate — Unified Multi-Product System

> **Three independent products. One chain of custody. Zero data loss.**

Precision Gate is a composition layer that unifies three autonomous products:

| Product | Role |
|---------|------|
| **TCRIA** | Evidence governance, document organization, custody workflow |
| **Quinta Ordem Gate** | Deterministic quality verification engine |
| **Precision Gate Core** | Mobile custody layer that orchestrates both |

Each product is independently deployable, testable, and auditable. They communicate only through **versioned adapter contracts**. No product mutates another's outputs.

## Quick Start

```bash
# Run TCRIA standalone
tcria scan ~/Downloads --strict

# Run Quinta Ordem standalone
python -m quinta_ordem

# Run the unified pipeline
python -c "
from products.precision_gate_core.precision_gate.composition.pipeline import PrecisionGatePipeline
pipeline = PrecisionGatePipeline.default()
record, trail = pipeline.run(bundle, case_id='case-001')
print(record.status, record.confidence)
"
```

## Repository Structure

```
precision-gate/
├── products/
│   ├── tcria/                    # TCRIA governance product
│   ├── quinta-ordem-gate/        # Deterministic verification product
│   └── precision-gate-core/      # Orchestration product
├── shared/
│   ├── contracts/                # Versioned adapter schemas (JSON)
│   ├── models/                   # Shared domain types
│   └── cli/                      # Unified CLI
├── integration/                  # Docker, deployment, API specs
├── tests/integration/            # Cross-product tests
└── docs/                         # Architecture and custody docs
```

## Core Principles

1. **Product Independence** — Each product has its own `pyproject.toml`, tests, CLI.
2. **Adapter Pattern** — Products communicate through versioned adapter contracts only.
3. **Non-Abandonment** — No TCRIA principle may be bypassed or silently overridden.
4. **Chain of Custody** — Every transition is logged with SHA-256 hashes.
5. **Immutable Snapshots** — Original outputs are never mutated.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — Multi-product composition model
- [CUSTODY_CHARTER.md](CUSTODY_CHARTER.md) — Non-abandonment principles
- [docs/COMPOSITION_MODEL.md](docs/COMPOSITION_MODEL.md) — Data flow diagrams
- [docs/ADAPTER_CONTRACTS.md](docs/ADAPTER_CONTRACTS.md) — Versioned adapter APIs
- [docs/CUSTODY_FLOW.md](docs/CUSTODY_FLOW.md) — Chain-of-custody preservation
- [products/tcria/README.md](products/tcria/README.md) — TCRIA standalone guide
- [products/quinta-ordem-gate/README.md](products/quinta-ordem-gate/README.md) — Quinta Ordem guide
- [products/precision-gate-core/README.md](products/precision-gate-core/README.md) — Precision Gate guide

## Running Tests

```bash
# TCRIA product tests
pytest tests/test_engine_smoke.py -q

# Integration tests (cross-product)
pytest tests/integration/ -q
```
