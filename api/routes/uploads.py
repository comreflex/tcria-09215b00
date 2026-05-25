from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from tcria.engine import TCRIAEngine
from tcria.storage import TransientScanStore


def create_uploads_router(
    *,
    engine: TCRIAEngine,
    scan_store: TransientScanStore,
    max_upload_mb: int,
) -> APIRouter:
    router = APIRouter()

    @router.get("/ui/upload", response_class=HTMLResponse)
    def upload_ui() -> str:
        return """
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>TCRIA Upload</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background:#f8fafc; color:#0f172a; margin:0; }
      .wrap { max-width: 760px; margin: 40px auto; background:white; border:1px solid #e2e8f0; border-radius:16px; padding:24px; }
      h1 { margin:0 0 8px 0; }
      p { color:#475569; }
      .plus { width:64px; height:64px; border-radius:999px; border:2px dashed #94a3b8; display:flex; align-items:center; justify-content:center; font-size:40px; color:#334155; cursor:pointer; margin: 18px 0;}
      input[type=file] { display:none; }
      button { background:#0f172a; color:white; border:none; border-radius:10px; padding:10px 14px; cursor:pointer; }
      pre { background:#0b1020; color:#cbd5e1; border-radius:10px; padding:12px; overflow:auto; max-height:420px; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1>TCRIA Scanner</h1>
      <p>Selecione um arquivo para auditoria. O armazenamento é temporário e será apagado automaticamente.</p>
      <label class="plus" for="f">+</label>
      <input id="f" type="file" />
      <div><button id="send">Escanear Arquivo</button></div>
      <p id="status"></p>
      <pre id="out">{}</pre>
    </div>
    <script>
      const fileInput = document.getElementById('f');
      const send = document.getElementById('send');
      const out = document.getElementById('out');
      const status = document.getElementById('status');
      send.onclick = async () => {
        if (!fileInput.files || fileInput.files.length === 0) {
          status.textContent = 'Selecione um arquivo antes de escanear.';
          return;
        }
        status.textContent = 'Processando...';
        const fd = new FormData();
        fd.append('file', fileInput.files[0]);
        fd.append('strict', 'true');
        const res = await fetch('/uploads/scan', { method: 'POST', body: fd });
        const data = await res.json();
        status.textContent = res.ok ? 'Concluído.' : 'Falha.';
        out.textContent = JSON.stringify(data, null, 2);
      };
    </script>
  </body>
</html>
"""

    def _write_upload_to_disk(target: Path, upload: UploadFile) -> int:
        max_bytes = max_upload_mb * 1024 * 1024
        total = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as fh:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"Arquivo excede limite de {max_upload_mb}MB.")
                fh.write(chunk)
        return total

    @router.post("/uploads/scan")
    def upload_and_scan(
        file: UploadFile = File(...),
        strict: bool = Form(True),
    ) -> dict[str, object]:
        scan_store.purge_expired()
        original_name = Path(file.filename or "upload.bin").name
        scan = scan_store.create_scan(original_name)
        scan_store.update_status(scan.scan_id, "PROCESSING")
        input_path = Path(scan.input_path)
        out_dir = Path(scan.out_dir)

        try:
            written = _write_upload_to_disk(input_path, file)
            result = engine.run_audit(
                input_path=str(input_path),
                strict=strict,
                out_dir=str(out_dir),
                output_stem=scan.scan_id,
                include_pdf=False,
            )
            bundle = result.get("bundle", {})
            response_payload = {
                "scan_id": scan.scan_id,
                "status": "COMPLETED",
                "received_bytes": written,
                "expires_at": scan.expires_at,
                "summary": {
                    "total_files_scanned": bundle.get("total_files_scanned"),
                    "accusation_set_count": bundle.get("accusation_set_count"),
                    "classification_counts": bundle.get("classification_counts"),
                },
                "artifacts": result.get("artifacts", {}),
            }
            scan_store.save_result(scan.scan_id, response_payload)
            return response_payload
        except HTTPException:
            scan_store.update_status(scan.scan_id, "FAILED", error="upload_validation_error")
            raise
        except Exception as exc:
            scan_store.update_status(scan.scan_id, "FAILED", error=str(exc))
            raise HTTPException(status_code=400, detail=f"Falha ao processar upload: {exc}") from exc

    @router.get("/uploads/{scan_id}")
    def get_upload_status(scan_id: str) -> dict[str, object]:
        scan_store.purge_expired()
        record = scan_store.get_scan(scan_id)
        if record is None:
            raise HTTPException(status_code=404, detail="scan_id não encontrado.")
        return record.to_dict()

    @router.post("/uploads/purge")
    def purge_expired_uploads() -> dict[str, object]:
        purged = scan_store.purge_expired()
        return {
            "purged": purged,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    return router
