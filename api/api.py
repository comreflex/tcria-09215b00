from __future__ import annotations

import os

from fastapi import FastAPI

from api.routes.audit import create_audit_router
from api.routes.cases import create_cases_router
from api.routes.core import router as core_router
from api.routes.uploads import create_uploads_router
from tcria.engine import TCRIAEngine
from tcria.settings import load_env
from tcria.storage import TransientScanStore


load_env()
app = FastAPI(title="TCRIA API", version="0.2.0")
engine = TCRIAEngine()
_data_dir = os.getenv("TCRIA_DATA_DIR", "/tmp/tcria_data")
_retention_minutes = int(os.getenv("TCRIA_RETENTION_MINUTES", "60"))
_max_upload_mb = int(os.getenv("TCRIA_MAX_UPLOAD_MB", "25"))
scan_store = TransientScanStore(_data_dir, retention_minutes=_retention_minutes)

app.include_router(core_router)
app.include_router(create_uploads_router(engine=engine, scan_store=scan_store, max_upload_mb=_max_upload_mb))
app.include_router(create_audit_router(engine=engine))
app.include_router(create_cases_router())
