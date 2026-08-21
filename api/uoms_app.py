from __future__ import annotations

from fastapi import FastAPI

from api.uoms import router

app = FastAPI(title="TCRIA UOMS Boundary", version="1.0.0")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "stage": "tcria"}
