from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ScanRecord:
    scan_id: str
    created_at: str
    expires_at: str
    status: str
    original_name: str
    input_path: str
    out_dir: str
    result_json: str | None
    deleted_at: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "original_name": self.original_name,
            "input_path": self.input_path,
            "out_dir": self.out_dir,
            "result_json": json.loads(self.result_json) if self.result_json else None,
            "deleted_at": self.deleted_at,
            "error": self.error,
        }


class TransientScanStore:
    def __init__(self, data_dir: str | Path, retention_minutes: int = 60) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.scans_dir = self.data_dir / "scans"
        self.scans_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "scans.db"
        self.retention_minutes = max(1, int(retention_minutes))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS scans (
                    scan_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    input_path TEXT NOT NULL,
                    out_dir TEXT NOT NULL,
                    result_json TEXT,
                    deleted_at TEXT,
                    error TEXT
                )
                """
            )
            conn.commit()

    def create_scan(self, original_name: str) -> ScanRecord:
        scan_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(minutes=self.retention_minutes)
        scan_dir = self.scans_dir / scan_id
        scan_dir.mkdir(parents=True, exist_ok=True)
        input_path = scan_dir / "input" / original_name
        input_path.parent.mkdir(parents=True, exist_ok=True)
        out_dir = scan_dir / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        record = ScanRecord(
            scan_id=scan_id,
            created_at=created_at.isoformat(timespec="seconds"),
            expires_at=expires_at.isoformat(timespec="seconds"),
            status="UPLOADED",
            original_name=original_name,
            input_path=str(input_path),
            out_dir=str(out_dir),
            result_json=None,
            deleted_at=None,
            error=None,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scans (scan_id, created_at, expires_at, status, original_name, input_path, out_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.scan_id,
                    record.created_at,
                    record.expires_at,
                    record.status,
                    record.original_name,
                    record.input_path,
                    record.out_dir,
                ),
            )
            conn.commit()
        return record

    def update_status(self, scan_id: str, status: str, *, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE scans SET status = ?, error = ? WHERE scan_id = ?", (status, error, scan_id))
            conn.commit()

    def save_result(self, scan_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE scans SET result_json = ?, status = ? WHERE scan_id = ?", (json.dumps(payload, ensure_ascii=False), "COMPLETED", scan_id))
            conn.commit()

    def get_scan(self, scan_id: str) -> ScanRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
        if row is None:
            return None
        return ScanRecord(
            scan_id=row["scan_id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            status=row["status"],
            original_name=row["original_name"],
            input_path=row["input_path"],
            out_dir=row["out_dir"],
            result_json=row["result_json"],
            deleted_at=row["deleted_at"],
            error=row["error"],
        )

    def purge_expired(self) -> int:
        now = datetime.now(timezone.utc)
        deleted_count = 0
        with self._connect() as conn:
            rows = conn.execute("SELECT scan_id, expires_at, out_dir, input_path, deleted_at FROM scans").fetchall()
            for row in rows:
                if row["deleted_at"]:
                    continue
                try:
                    exp = datetime.fromisoformat(row["expires_at"])
                except Exception:
                    exp = now
                if exp <= now:
                    scan_root = Path(row["out_dir"]).parent
                    if scan_root.exists():
                        shutil.rmtree(scan_root, ignore_errors=True)
                    conn.execute(
                        "UPDATE scans SET status = ?, deleted_at = ? WHERE scan_id = ?",
                        ("DELETED", _utc_now_iso(), row["scan_id"]),
                    )
                    deleted_count += 1
            conn.commit()
        return deleted_count
