"""sqlite review store, scoped by (tenant, session). Replaces global STATE with
a real schema; reads are tenant+session scoped (fail-closed by construction)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from truelinev2.context import RequestContext


class ReviewStore:
    def __init__(self, db_path):
        self._p = str(db_path)
        Path(self._p).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS reviews ("
                "tenant TEXT NOT NULL, session TEXT NOT NULL, "
                "payload_json TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "PRIMARY KEY (tenant, session))")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._p)

    def save_review(self, ctx: RequestContext, payload_json: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with self._conn() as con:
            con.execute(
                "INSERT OR REPLACE INTO reviews (tenant, session, payload_json, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (ctx.tenant.value, ctx.session_id, payload_json, ts))

    def get_review(self, ctx: RequestContext) -> Optional[str]:
        with self._conn() as con:
            cur = con.execute(
                "SELECT payload_json FROM reviews WHERE tenant = ? AND session = ?",
                (ctx.tenant.value, ctx.session_id))
            row = cur.fetchone()
        return row[0] if row else None
