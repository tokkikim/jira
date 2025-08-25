import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class OverlayStore:
    def __init__(self, db_path: str = "overlays.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._conn() as con:
            con.execute("PRAGMA journal_mode=WAL;")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS overlays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL CHECK(scope IN ('team','user')),
                    owner TEXT NOT NULL DEFAULT '',
                    project_key TEXT,
                    issue_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(scope, owner, issue_key)
                );
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_overlays_issue ON overlays(issue_key);"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_overlays_project ON overlays(project_key);"
            )

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _normalize_owner(scope: str, owner: Optional[str]) -> str:
        if scope == "team":
            return ""
        return owner or ""

    def upsert_overlay(
        self,
        *,
        issue_key: str,
        payload: Dict[str, Any],
        project_key: Optional[str] = None,
        scope: str = "team",
        owner: Optional[str] = None,
    ) -> None:
        owner_norm = self._normalize_owner(scope, owner)
        now = self._now_iso()
        payload_str = json.dumps(payload, ensure_ascii=False)
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO overlays (scope, owner, project_key, issue_key, payload, updated_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, owner, issue_key) DO UPDATE SET
                    payload=excluded.payload,
                    project_key=COALESCE(excluded.project_key, project_key),
                    updated_at=excluded.updated_at
                """,
                (scope, owner_norm, project_key, issue_key, payload_str, now, now),
            )

    def delete_overlay(
        self, *, issue_key: str, scope: str = "team", owner: Optional[str] = None
    ) -> None:
        owner_norm = self._normalize_owner(scope, owner)
        with self._conn() as con:
            con.execute(
                "DELETE FROM overlays WHERE scope=? AND owner=? AND issue_key=?",
                (scope, owner_norm, issue_key),
            )

    def _fetch_overlays(
        self,
        *,
        scope: str,
        owner: Optional[str] = None,
        issue_keys: Optional[List[str]] = None,
        project_keys: Optional[List[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        owner_norm = self._normalize_owner(scope, owner)
        clauses: List[str] = ["scope=?", "owner=?"]
        params: List[Any] = [scope, owner_norm]
        if issue_keys:
            placeholders = ",".join(["?"] * len(issue_keys))
            clauses.append(f"issue_key IN ({placeholders})")
            params.extend(issue_keys)
        if project_keys:
            placeholders = ",".join(["?"] * len(project_keys))
            clauses.append(f"project_key IN ({placeholders})")
            params.extend(project_keys)
        where = " AND ".join(clauses)
        sql = f"SELECT issue_key, payload FROM overlays WHERE {where}"
        out: Dict[str, Dict[str, Any]] = {}
        with self._conn() as con:
            for issue_key, payload_str in con.execute(sql, params):
                try:
                    out[issue_key] = json.loads(payload_str)
                except Exception:
                    out[issue_key] = {}
        return out

    def get_overlays_merged(
        self,
        *,
        issue_keys: Optional[List[str]] = None,
        project_keys: Optional[List[str]] = None,
        user_owner: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        team = self._fetch_overlays(
            scope="team", owner=None, issue_keys=issue_keys, project_keys=project_keys
        )
        user = self._fetch_overlays(
            scope="user",
            owner=user_owner,
            issue_keys=issue_keys,
            project_keys=project_keys,
        )
        merged = dict(team)
        for k, v in user.items():
            merged[k] = {**merged.get(k, {}), **v}
        return merged

    def export_to_file(self, filepath: str) -> int:
        rows: List[Dict[str, Any]] = []
        with self._conn() as con:
            cur = con.execute(
                "SELECT scope, owner, project_key, issue_key, payload, updated_at, created_at FROM overlays"
            )
            for (
                scope,
                owner,
                project_key,
                issue_key,
                payload,
                updated_at,
                created_at,
            ) in cur:
                rows.append(
                    {
                        "scope": scope,
                        "owner": owner,
                        "project_key": project_key,
                        "issue_key": issue_key,
                        "payload": json.loads(payload),
                        "updated_at": updated_at,
                        "created_at": created_at,
                    }
                )
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        return len(rows)

    def import_from_file(self, filepath: str) -> int:
        with open(filepath, "r", encoding="utf-8") as f:
            rows = json.load(f)
        count = 0
        for row in rows:
            self.upsert_overlay(
                issue_key=row["issue_key"],
                payload=row.get("payload", {}),
                project_key=row.get("project_key"),
                scope=row.get("scope", "team"),
                owner=row.get("owner") or None,
            )
            count += 1
        return count

    def get_overlay(
        self, *, issue_key: str, scope: str = "team", owner: Optional[str] = None
    ) -> Dict[str, Any]:
        owner_norm = self._normalize_owner(scope, owner)
        with self._conn() as con:
            row = con.execute(
                "SELECT payload FROM overlays WHERE scope=? AND owner=? AND issue_key=?",
                (scope, owner_norm, issue_key),
            ).fetchone()
            if not row:
                return {}
            try:
                return json.loads(row[0])
            except Exception:
                return {}


def set_overlay(
    *,
    issue_key: str,
    payload: Dict[str, Any],
    project_key: Optional[str] = None,
    scope: str = "team",
    owner: Optional[str] = None,
) -> None:
    store = OverlayStore()
    current = store.get_overlay(issue_key=issue_key, scope=scope, owner=owner)
    merged = {**current, **payload}
    store.upsert_overlay(
        issue_key=issue_key,
        payload=merged,
        project_key=project_key,
        scope=scope,
        owner=owner,
    )


def set_overlay_dates(
    *,
    issue_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    project_key: Optional[str] = None,
    scope: str = "team",
    owner: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {}
    if start_date:
        payload["startDate"] = start_date
    if end_date:
        payload["dueDate"] = end_date
    if payload:
        set_overlay(
            issue_key=issue_key,
            payload=payload,
            project_key=project_key,
            scope=scope,
            owner=owner,
        )


def set_overlay_color(
    *,
    issue_key: str,
    color: str,
    project_key: Optional[str] = None,
    scope: str = "team",
    owner: Optional[str] = None,
) -> None:
    set_overlay(
        issue_key=issue_key,
        payload={"color": color},
        project_key=project_key,
        scope=scope,
        owner=owner,
    )


def set_overlay_hidden(
    *,
    issue_key: str,
    hidden: bool = True,
    project_key: Optional[str] = None,
    scope: str = "team",
    owner: Optional[str] = None,
) -> None:
    set_overlay(
        issue_key=issue_key,
        payload={"hidden": hidden},
        project_key=project_key,
        scope=scope,
        owner=owner,
    )
