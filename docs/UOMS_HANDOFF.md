# TCRIA boundary in UOMS

TCRIA remains the first independent auditor. `tcria.handoff.run_tcria_handoff` calls the existing
`TCRIAEngine`, preserves every native output, records `OPEN`, `RUNNING`, `OUTPUT`, and `CLOSE`, and
publishes `handoff.json` only after the original documents and native artifacts have been hashed.
The manifest is authenticated with `UOMS_TCRIA_HANDOFF_KEY`; SHA-256 protects integrity while the
stage HMAC establishes authenticity for Quinta Ordem.

The manifest is an operational transport envelope (`uoms.handoff.v1`), not a replacement for the
TCRIA audit bundle. The Quinta Ordem caller must receive both `manifest_path` and the exact
`manifest_sha256`; absence, mismatch, incompatible schema, missing artifact, or missing `CLOSE`
prevents the next stage from opening.

Run the isolated boundary with `uvicorn api.uoms_app:app`. The route is
`POST /uoms/tcria/open`. It requires a 32-byte-or-longer `UOMS_API_TOKEN` bearer token, a fixed
`UOMS_CUSTODY_ROOT`, and one or more `UOMS_EVIDENCE_ROOTS` separated by the platform path
separator. ZIP archives are rejected at this custody boundary; expand them inside an authorized
evidence root first. Handoff keys and optional CI-injected source commits must not be committed.

MCP is not used by this boundary. Existing MCP infrastructure is not treated as part of the UOMS
Audit Plane.
