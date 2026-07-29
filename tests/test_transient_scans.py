from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tcria.storage.transient_scans import TransientScanStore


def test_transient_scan_create_and_purge(tmp_path: Path) -> None:
    store = TransientScanStore(tmp_path / "data", retention_minutes=1)
    rec = store.create_scan("sample.txt")
    assert rec.scan_id
    assert Path(rec.input_path).parent.exists()
    assert Path(rec.out_dir).exists()

    # Force expiration and purge.
    with store._connect() as conn:  # noqa: SLF001 - test-only access
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")
        conn.execute("UPDATE scans SET expires_at = ? WHERE scan_id = ?", (past, rec.scan_id))
        conn.commit()
    purged = store.purge_expired()
    assert purged == 1
    reloaded = store.get_scan(rec.scan_id)
    assert reloaded is not None
    assert reloaded.status == "DELETED"
