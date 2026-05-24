from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class IdentityHashEntry:
    project_id: str
    tc_hash: str
    record: str
    dag_unique_name: str | None = None
    remote_updated_at: str | None = None


@dataclass(frozen=True)
class RedcapDataValue:
    project_id: str
    event_id: str | None
    record: str
    field_name: str
    value: str
    instance: str | None = None
    dag_unique_name: str | None = None
    remote_updated_at: str | None = None


@dataclass(frozen=True)
class RemoteRecordManifest:
    project_id: str
    record: str
    remote_updated_at: str
    dag_unique_name: str | None = None
    record_last_modified_at: str | None = None
    identity_hash_updated_at: str | None = None


@dataclass(frozen=True)
class SyncDelta:
    to_pull: list[str]
    conflicts: list[str]
    unchanged: list[str]


class DataEntryStore:
    """
    SQLite-backed local cache for the upcoming REDCap data-entry mode.

    The main value table intentionally mirrors REDCap's redcap_data shape:
    project_id, event_id, record, field_name, value, instance. Extra sync columns
    live next to those fields so later UI and dynamic-query work can reuse the
    same local data model without committing to the final form renderer yet.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS data_entry_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS project_context (
                    project_id TEXT PRIMARY KEY,
                    project_title TEXT,
                    username TEXT,
                    dag_unique_name TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS record_sync_state (
                    project_id TEXT NOT NULL,
                    record TEXT NOT NULL,
                    dag_unique_name TEXT,
                    remote_updated_at TEXT,
                    local_updated_at TEXT,
                    last_synced_at TEXT,
                    dirty INTEGER NOT NULL DEFAULT 0,
                    conflict INTEGER NOT NULL DEFAULT 0,
                    deleted_remote INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (project_id, record)
                );

                CREATE TABLE IF NOT EXISTS redcap_data_values (
                    project_id TEXT NOT NULL,
                    event_id TEXT NOT NULL DEFAULT '',
                    record TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    value TEXT NOT NULL DEFAULT '',
                    instance TEXT NOT NULL DEFAULT '',
                    dag_unique_name TEXT,
                    remote_updated_at TEXT,
                    local_updated_at TEXT,
                    source TEXT NOT NULL DEFAULT 'remote',
                    dirty INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (project_id, event_id, record, field_name, instance)
                );

                CREATE VIEW IF NOT EXISTS redcap_data AS
                    SELECT project_id, event_id, record, field_name, value, instance
                    FROM redcap_data_values;

                CREATE TABLE IF NOT EXISTS identity_hash_map (
                    project_id TEXT NOT NULL,
                    tc_hash TEXT NOT NULL,
                    record TEXT NOT NULL,
                    dag_unique_name TEXT,
                    remote_updated_at TEXT,
                    last_synced_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, tc_hash)
                );

                CREATE TABLE IF NOT EXISTS pending_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    event_id TEXT NOT NULL DEFAULT '',
                    record TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    instance TEXT NOT NULL DEFAULT '',
                    old_value TEXT,
                    new_value TEXT NOT NULL DEFAULT '',
                    base_remote_updated_at TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    source TEXT NOT NULL DEFAULT 'manual',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS metadata_cache (
                    project_id TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, cache_key)
                );

                CREATE TABLE IF NOT EXISTS dynamic_query_cache (
                    project_id TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    record TEXT NOT NULL DEFAULT '',
                    event_id TEXT NOT NULL DEFAULT '',
                    instance TEXT NOT NULL DEFAULT '',
                    dag_unique_name TEXT,
                    context_hash TEXT NOT NULL DEFAULT '',
                    options_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY (
                        project_id,
                        field_name,
                        record,
                        event_id,
                        instance,
                        context_hash
                    )
                );

                CREATE INDEX IF NOT EXISTS idx_redcap_data_record
                    ON redcap_data_values (project_id, record);
                CREATE INDEX IF NOT EXISTS idx_redcap_data_field
                    ON redcap_data_values (project_id, field_name);
                CREATE INDEX IF NOT EXISTS idx_identity_hash_record
                    ON identity_hash_map (project_id, record);
                CREATE INDEX IF NOT EXISTS idx_pending_changes_status
                    ON pending_changes (project_id, status);
                """
            )
            db.execute(
                """
                INSERT INTO data_entry_meta(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def schema_version(self) -> int:
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM data_entry_meta WHERE key = 'schema_version'"
            ).fetchone()
        return int(row["value"]) if row is not None else 0

    def upsert_project_context(
        self,
        *,
        project_id: str,
        project_title: str | None = None,
        username: str | None = None,
        dag_unique_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        updated_at = utc_now()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO project_context(
                    project_id,
                    project_title,
                    username,
                    dag_unique_name,
                    context_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    project_title = excluded.project_title,
                    username = excluded.username,
                    dag_unique_name = excluded.dag_unique_name,
                    context_json = excluded.context_json,
                    updated_at = excluded.updated_at
                """,
                (
                    str(project_id),
                    project_title,
                    username,
                    dag_unique_name,
                    json.dumps(context or {}, ensure_ascii=False, sort_keys=True),
                    updated_at,
                ),
            )

    def upsert_identity_hashes(self, entries: Iterable[IdentityHashEntry]) -> None:
        synced_at = utc_now()
        rows = [
            (
                entry.project_id,
                entry.tc_hash,
                entry.record,
                entry.dag_unique_name,
                entry.remote_updated_at,
                synced_at,
            )
            for entry in entries
        ]
        with self.connect() as db:
            db.executemany(
                """
                INSERT INTO identity_hash_map(
                    project_id,
                    tc_hash,
                    record,
                    dag_unique_name,
                    remote_updated_at,
                    last_synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, tc_hash) DO UPDATE SET
                    record = excluded.record,
                    dag_unique_name = excluded.dag_unique_name,
                    remote_updated_at = excluded.remote_updated_at,
                    last_synced_at = excluded.last_synced_at
                """,
                rows,
            )

    def lookup_record_by_tc_hash(self, project_id: str, tc_hash: str) -> str | None:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT record FROM identity_hash_map
                WHERE project_id = ? AND tc_hash = ?
                """,
                (str(project_id), str(tc_hash)),
            ).fetchone()
        return str(row["record"]) if row is not None else None

    def upsert_remote_values(self, values: Iterable[RedcapDataValue]) -> None:
        synced_at = utc_now()
        with self.connect() as db:
            for value in values:
                event_id = normalize_key_part(value.event_id)
                instance = normalize_key_part(value.instance)
                remote_updated_at = value.remote_updated_at
                db.execute(
                    """
                    INSERT INTO redcap_data_values(
                        project_id,
                        event_id,
                        record,
                        field_name,
                        value,
                        instance,
                        dag_unique_name,
                        remote_updated_at,
                        local_updated_at,
                        source,
                        dirty
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'remote', 0)
                    ON CONFLICT(project_id, event_id, record, field_name, instance)
                    DO UPDATE SET
                        value = excluded.value,
                        dag_unique_name = excluded.dag_unique_name,
                        remote_updated_at = excluded.remote_updated_at,
                        local_updated_at = excluded.local_updated_at,
                        source = 'remote',
                        dirty = 0
                    """,
                    (
                        str(value.project_id),
                        event_id,
                        str(value.record),
                        str(value.field_name),
                        str(value.value),
                        instance,
                        value.dag_unique_name,
                        remote_updated_at,
                        synced_at,
                    ),
                )
                self._upsert_record_sync_state(
                    db,
                    project_id=str(value.project_id),
                    record=str(value.record),
                    dag_unique_name=value.dag_unique_name,
                    remote_updated_at=remote_updated_at,
                    local_updated_at=synced_at,
                    last_synced_at=synced_at,
                    dirty=False,
                    conflict=False,
                )

    def upsert_remote_manifest(self, manifest: Iterable[RemoteRecordManifest]) -> None:
        synced_at = utc_now()
        with self.connect() as db:
            for item in manifest:
                self._upsert_record_sync_state(
                    db,
                    project_id=str(item.project_id),
                    record=str(item.record),
                    dag_unique_name=item.dag_unique_name,
                    remote_updated_at=item.remote_updated_at,
                    local_updated_at=synced_at,
                    last_synced_at=synced_at,
                    dirty=False,
                    conflict=False,
                )

    def mark_record_conflicts(
        self,
        *,
        project_id: str,
        records: Iterable[str],
        conflict: bool = True,
    ) -> None:
        with self.connect() as db:
            for record in records:
                self._upsert_record_sync_state(
                    db,
                    project_id=str(project_id),
                    record=str(record),
                    conflict=conflict,
                )

    def redcap_data_rows(self, project_id: str, record: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT project_id, event_id, record, field_name, value, instance
            FROM redcap_data_values
            WHERE project_id = ?
        """
        params: list[Any] = [str(project_id)]
        if record is not None:
            query += " AND record = ?"
            params.append(str(record))
        query += " ORDER BY record, event_id, instance, field_name"
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def queue_local_change(
        self,
        *,
        project_id: str,
        record: str,
        field_name: str,
        new_value: str,
        event_id: str | None = None,
        instance: str | None = None,
        base_remote_updated_at: str | None = None,
        source: str = "manual",
        payload: dict[str, Any] | None = None,
    ) -> int:
        event_key = normalize_key_part(event_id)
        instance_key = normalize_key_part(instance)
        created_at = utc_now()
        with self.connect() as db:
            existing = db.execute(
                """
                SELECT value, dag_unique_name, remote_updated_at
                FROM redcap_data_values
                WHERE project_id = ? AND event_id = ? AND record = ? AND field_name = ? AND instance = ?
                """,
                (str(project_id), event_key, str(record), str(field_name), instance_key),
            ).fetchone()
            old_value = str(existing["value"]) if existing is not None else None
            remote_updated_at = (
                base_remote_updated_at
                or (str(existing["remote_updated_at"]) if existing is not None and existing["remote_updated_at"] else None)
            )
            db.execute(
                """
                INSERT INTO redcap_data_values(
                    project_id,
                    event_id,
                    record,
                    field_name,
                    value,
                    instance,
                    dag_unique_name,
                    remote_updated_at,
                    local_updated_at,
                    source,
                    dirty
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'local', 1)
                ON CONFLICT(project_id, event_id, record, field_name, instance)
                DO UPDATE SET
                    value = excluded.value,
                    local_updated_at = excluded.local_updated_at,
                    source = 'local',
                    dirty = 1
                """,
                (
                    str(project_id),
                    event_key,
                    str(record),
                    str(field_name),
                    str(new_value),
                    instance_key,
                    str(existing["dag_unique_name"]) if existing is not None and existing["dag_unique_name"] else None,
                    remote_updated_at,
                    created_at,
                ),
            )
            cursor = db.execute(
                """
                INSERT INTO pending_changes(
                    project_id,
                    event_id,
                    record,
                    field_name,
                    instance,
                    old_value,
                    new_value,
                    base_remote_updated_at,
                    created_at,
                    status,
                    source,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    str(project_id),
                    event_key,
                    str(record),
                    str(field_name),
                    instance_key,
                    old_value,
                    str(new_value),
                    remote_updated_at,
                    created_at,
                    str(source),
                    json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
                ),
            )
            self._upsert_record_sync_state(
                db,
                project_id=str(project_id),
                record=str(record),
                local_updated_at=created_at,
                dirty=True,
            )
            return int(cursor.lastrowid)

    def pending_changes(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM pending_changes WHERE status = 'queued'"
        params: list[Any] = []
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(str(project_id))
        query += " ORDER BY created_at, id"
        with self.connect() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def mark_change_status(self, change_id: int, status: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE pending_changes SET status = ? WHERE id = ?",
                (str(status), int(change_id)),
            )

    def compare_remote_manifest(self, manifest: Iterable[RemoteRecordManifest]) -> SyncDelta:
        to_pull: list[str] = []
        conflicts: list[str] = []
        unchanged: list[str] = []
        with self.connect() as db:
            for item in manifest:
                row = db.execute(
                    """
                    SELECT remote_updated_at, dirty
                    FROM record_sync_state
                    WHERE project_id = ? AND record = ?
                    """,
                    (str(item.project_id), str(item.record)),
                ).fetchone()
                if row is None:
                    to_pull.append(item.record)
                    continue
                local_remote_updated_at = row["remote_updated_at"]
                server_newer = timestamp_is_newer(item.remote_updated_at, local_remote_updated_at)
                if server_newer and int(row["dirty"] or 0):
                    conflicts.append(item.record)
                elif server_newer:
                    to_pull.append(item.record)
                else:
                    unchanged.append(item.record)
        return SyncDelta(to_pull=to_pull, conflicts=conflicts, unchanged=unchanged)

    def cache_metadata(self, project_id: str, cache_key: str, payload: Any) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO metadata_cache(project_id, cache_key, payload_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    str(project_id),
                    str(cache_key),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )

    def load_metadata(self, project_id: str, cache_key: str) -> Any | None:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT payload_json FROM metadata_cache
                WHERE project_id = ? AND cache_key = ?
                """,
                (str(project_id), str(cache_key)),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["payload_json"]))

    def _upsert_record_sync_state(
        self,
        db: sqlite3.Connection,
        *,
        project_id: str,
        record: str,
        dag_unique_name: str | None = None,
        remote_updated_at: str | None = None,
        local_updated_at: str | None = None,
        last_synced_at: str | None = None,
        dirty: bool | None = None,
        conflict: bool | None = None,
    ) -> None:
        existing = db.execute(
            """
            SELECT dag_unique_name, remote_updated_at, local_updated_at, last_synced_at, dirty, conflict
            FROM record_sync_state
            WHERE project_id = ? AND record = ?
            """,
            (project_id, record),
        ).fetchone()
        if existing is None:
            db.execute(
                """
                INSERT INTO record_sync_state(
                    project_id,
                    record,
                    dag_unique_name,
                    remote_updated_at,
                    local_updated_at,
                    last_synced_at,
                    dirty,
                    conflict
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    record,
                    dag_unique_name,
                    remote_updated_at,
                    local_updated_at,
                    last_synced_at,
                    1 if dirty else 0,
                    1 if conflict else 0,
                ),
            )
            return
        db.execute(
            """
            UPDATE record_sync_state
            SET
                dag_unique_name = COALESCE(?, dag_unique_name),
                remote_updated_at = COALESCE(?, remote_updated_at),
                local_updated_at = COALESCE(?, local_updated_at),
                last_synced_at = COALESCE(?, last_synced_at),
                dirty = COALESCE(?, dirty),
                conflict = COALESCE(?, conflict)
            WHERE project_id = ? AND record = ?
            """,
            (
                dag_unique_name,
                remote_updated_at,
                local_updated_at,
                last_synced_at,
                None if dirty is None else 1 if dirty else 0,
                None if conflict is None else 1 if conflict else 0,
                project_id,
                record,
            ),
        )


def normalize_key_part(value: str | None) -> str:
    if value in {None, ""}:
        return ""
    return str(value)


def timestamp_is_newer(candidate: str | None, baseline: str | None) -> bool:
    if not candidate:
        return False
    if not baseline:
        return True
    return str(candidate) > str(baseline)


def utc_now() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
