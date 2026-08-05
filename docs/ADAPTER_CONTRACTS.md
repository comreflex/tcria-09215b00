# Adapter Contracts

All adapters between products are versioned, logged, and immutable.

## TCRIA Bundle → Quinta Ordem Payload (v1.0)

**Adapter:** `precision_gate.adapters.tcria_adapter.TCRIAAdapter`  
**Schema:** `shared/contracts/tcria_bundle_v1.0.json`

### Input: TCRIA Audit Bundle

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audit_id` | string | ✓ | Unique audit identifier |
| `total_files_scanned` | integer | ✓ | Number of files processed |
| `prescriptive_gate_status` | string | — | `approved`/`blocked`/`conditional` |
| `files` | array | — | List of evidence items |
| `decisions` | array | — | List of decision records |
| `metadata` | object | — | Governance metadata |

### Output: Quinta Ordem Payload

| Field | Type | Description |
|-------|------|-------------|
| `quinta_ordem_adapter_version` | `"1.0"` | Contract version |
| `execution_id` | string | From `audit_id` |
| `evidence` | array | Mapped from `files` |
| `decisions` | array | Original decisions |
| `gate_results` | array | TCRIA gate statuses |
| `metadata` | object | Includes `open_points` |
| `_precision_gate_meta` | object | Conversion audit log |

### Non-Abandonment Checks

If `prescriptive_gate_status == "blocked"`:
- `_precision_gate_meta.non_abandonment_checks` will contain a flag.
- The downstream `CustodyStateMachine` will enforce `human_review_required = True`.

---

## Quinta Ordem Decision → Custody State (v1.0)

**Adapter:** `precision_gate.adapters.quinta_ordem_adapter.QuintaOrdemAdapter`  
**Schema:** `shared/contracts/quinta_ordem_v1.0.json`

### Input: `GateDecision` (quinta_ordem)

| Field | Description |
|-------|-------------|
| `execution_id` | Passed through |
| `status` | `approved`/`conditional`/`returned_for_correction`/`blocked` |
| `confidence` | Float 0.0–1.0 |
| `breakdown` | `ConfidenceBreakdown` (5 dimensions) |
| `findings` | List of `Finding` |
| `human_review_required` | Boolean |
| `execution_context_sha256` | SHA-256 of the input context |

### Output: Custody State Dict

```json
{
  "schema_version": "1.0",
  "custody_state_at": "<ISO 8601>",
  "execution_id": "...",
  "status": "approved",
  "confidence": 0.97,
  "confidence_breakdown": {...},
  "human_review_required": false,
  "non_abandonment_flags": [],
  "quinta_ordem_decision": {...},
  "custody_trail": {
    "execution_context_sha256": "...",
    "decision_sha256": "..."
  }
}
```

---

## Precision Gate Report (v1.0)

**Builder:** `precision_gate.reporting.report_builder.ReportBuilder`  
**Schema:** `shared/contracts/precision_gate_manifest.json`

The report is the final output of the pipeline, including:
- Final custody status and confidence
- All custody hashes (TCRIA → Quinta Ordem chain)
- Non-abandonment flags
- Full append-only audit trail
- Human-readable Markdown summary
