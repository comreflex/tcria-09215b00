# TCRIA — Evidence Governance Product

TCRIA (TCR-IA) is the evidence governance and document organization engine.
It provides chain-of-custody for legal evidence ingestion, classification,
prescriptive/compliance/traceability gating, and audit bundle generation.

## Quick Start

```bash
pip install -e .[dev]
tcria scan ~/Downloads --strict
```

## Core Modules

| Module | Responsibility |
|--------|---------------|
| `tcria/engine.py` | Orchestrates the full audit pipeline |
| `tcria/governance/` | Prescriptive, compliance, and traceability gates |
| `tcria/ingestion/` | PDF, DOCX, XLSX, HTML, TXT readers |
| `tcria/audit/` | Audit bundle builder and report generator |
| `tcria/signals/` | Currency, date, entity detectors |
| `tcria/classification/` | Artifact classifier |
| `tcria/cli.py` | Command-line interface |

## Standalone Deployment

TCRIA can be deployed independently via Docker:

```bash
docker build -f ../../Dockerfile.mcp -t tcria:standalone .
docker run -p 8000:8000 tcria:standalone
```

## Adapter Contract (Outbound)

When used within the Precision Gate composition, TCRIA produces an **audit bundle**
conforming to `../../shared/contracts/tcria_bundle_v1.0.json`.

The `TCRIAExecutionContextAdapter` (in `quinta-ordem-gate`) converts this bundle
into a `quinta_ordem.ExecutionContext` for Quinta Ordem Gate evaluation.

## Tests

```bash
cd ../../
pytest tests/test_engine_smoke.py -q
```

## Principles

- **Non-abandonment**: No TCRIA governance gate may be bypassed or weakened.
- **Immutability**: Audit bundles are write-once, hash-verified snapshots.
- **Auditability**: Every artifact decision is recorded with provenance.
