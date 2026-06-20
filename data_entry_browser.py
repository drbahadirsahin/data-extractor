from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable

from data_entry_store import DataEntryStore, normalize_key_part


UNKNOWN_FORM_NAME = "__unknown__"


@dataclass
class RecordSummary:
    project_id: str
    record: str
    label: str
    dag_unique_name: str | None = None
    remote_updated_at: str | None = None
    local_updated_at: str | None = None
    last_synced_at: str | None = None
    dirty: bool = False
    conflict: bool = False
    value_count: int = 0
    identity_hash_count: int = 0
    pending_change_count: int = 0


@dataclass(frozen=True)
class FieldDefinition:
    field_name: str
    form_name: str
    field_label: str = ""
    field_type: str = ""


@dataclass(frozen=True)
class RecordFieldValue:
    field_name: str
    value: str
    event_id: str = ""
    repeat_instrument: str = ""
    instance: str = ""
    form_name: str = UNKNOWN_FORM_NAME
    field_label: str = ""
    field_type: str = ""
    source: str = "remote"
    dirty: bool = False
    present: bool = True
    remote_updated_at: str | None = None
    local_updated_at: str | None = None


@dataclass(frozen=True)
class RecordFormSection:
    form_name: str
    fields: list[RecordFieldValue] = field(default_factory=list)


@dataclass(frozen=True)
class RecordDetail:
    project_id: str
    record: str
    dag_unique_name: str | None = None
    remote_updated_at: str | None = None
    local_updated_at: str | None = None
    last_synced_at: str | None = None
    dirty: bool = False
    conflict: bool = False
    identity_hashes: list[str] = field(default_factory=list)
    pending_changes: list[dict[str, Any]] = field(default_factory=list)
    forms: list[RecordFormSection] = field(default_factory=list)

    @property
    def field_values(self) -> list[RecordFieldValue]:
        return [value for section in self.forms for value in section.fields]


class DataEntryRecordBrowser:
    def __init__(self, store: DataEntryStore) -> None:
        self.store = store

    def list_records(
        self,
        project_id: str,
        *,
        search: str | None = None,
        dag_unique_name: str | None = None,
        dag_identifiers: Iterable[str] | None = None,
        label_fields: Iterable[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RecordSummary]:
        self.store.initialize()
        project_id = str(project_id)
        params: list[Any] = [project_id, project_id, project_id, project_id]
        filters = ["records.project_id = ?"]
        dag_filter_values = unique_non_empty([dag_unique_name, *(dag_identifiers or [])])
        if dag_filter_values:
            placeholders = ", ".join("?" for _ in dag_filter_values)
            filters.append(
                f"""
                COALESCE(
                    state.dag_unique_name,
                    (
                        SELECT value_rows.dag_unique_name
                        FROM redcap_data_values value_rows
                        WHERE value_rows.project_id = records.project_id
                          AND value_rows.record = records.record
                          AND value_rows.dag_unique_name IS NOT NULL
                        LIMIT 1
                    ),
                    (
                        SELECT hash_rows.dag_unique_name
                        FROM identity_hash_map hash_rows
                        WHERE hash_rows.project_id = records.project_id
                          AND hash_rows.record = records.record
                          AND hash_rows.dag_unique_name IS NOT NULL
                        LIMIT 1
                    )
                ) IN ({placeholders})
                """
            )
            params.extend(dag_filter_values)
        if search:
            pattern = f"%{search}%"
            filters.append(
                """
                (
                    records.record LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM redcap_data_values search_values
                        WHERE search_values.project_id = records.project_id
                          AND search_values.record = records.record
                          AND search_values.value LIKE ?
                    )
                    OR EXISTS (
                        SELECT 1
                        FROM identity_hash_map search_hashes
                        WHERE search_hashes.project_id = records.project_id
                          AND search_hashes.record = records.record
                          AND search_hashes.tc_hash LIKE ?
                    )
                )
                """
            )
            params.extend([pattern, pattern, pattern])
        params.extend([max(1, int(limit)), max(0, int(offset))])
        query = f"""
            WITH records AS (
                SELECT project_id, record FROM record_sync_state WHERE project_id = ?
                UNION
                SELECT project_id, record FROM redcap_data_values WHERE project_id = ?
                UNION
                SELECT project_id, record FROM identity_hash_map WHERE project_id = ?
            )
            SELECT
                records.project_id,
                records.record,
                COALESCE(
                    state.dag_unique_name,
                    (
                        SELECT value_rows.dag_unique_name
                        FROM redcap_data_values value_rows
                        WHERE value_rows.project_id = records.project_id
                          AND value_rows.record = records.record
                          AND value_rows.dag_unique_name IS NOT NULL
                        LIMIT 1
                    ),
                    (
                        SELECT hash_rows.dag_unique_name
                        FROM identity_hash_map hash_rows
                        WHERE hash_rows.project_id = records.project_id
                          AND hash_rows.record = records.record
                          AND hash_rows.dag_unique_name IS NOT NULL
                        LIMIT 1
                    )
                ) AS dag_unique_name,
                state.remote_updated_at,
                state.local_updated_at,
                state.last_synced_at,
                COALESCE(state.dirty, 0) AS dirty,
                COALESCE(state.conflict, 0) AS conflict,
                (
                    SELECT COUNT(*)
                    FROM redcap_data_values value_rows
                    WHERE value_rows.project_id = records.project_id
                      AND value_rows.record = records.record
                ) AS value_count,
                (
                    SELECT COUNT(*)
                    FROM identity_hash_map hash_rows
                    WHERE hash_rows.project_id = records.project_id
                      AND hash_rows.record = records.record
                ) AS identity_hash_count,
                (
                    SELECT COUNT(*)
                    FROM pending_changes pending
                    WHERE pending.project_id = records.project_id
                      AND pending.record = records.record
                      AND pending.status = 'queued'
                ) AS pending_change_count
            FROM records
            LEFT JOIN record_sync_state state
              ON state.project_id = records.project_id
             AND state.record = records.record
            WHERE {" AND ".join(filters)}
            ORDER BY records.record
            LIMIT ? OFFSET ?
        """
        with self.store.connect() as db:
            rows = db.execute(query, params).fetchall()
        summaries = [
            RecordSummary(
                project_id=str(row["project_id"]),
                record=str(row["record"]),
                label=str(row["record"]),
                dag_unique_name=optional_text(row["dag_unique_name"]),
                remote_updated_at=optional_text(row["remote_updated_at"]),
                local_updated_at=optional_text(row["local_updated_at"]),
                last_synced_at=optional_text(row["last_synced_at"]),
                dirty=bool(row["dirty"]),
                conflict=bool(row["conflict"]),
                value_count=int(row["value_count"] or 0),
                identity_hash_count=int(row["identity_hash_count"] or 0),
                pending_change_count=int(row["pending_change_count"] or 0),
            )
            for row in rows
        ]
        apply_summary_labels(self.store, project_id, summaries, label_fields)
        return summaries

    def get_record_detail(
        self,
        project_id: str,
        record: str,
        *,
        field_definitions: Iterable[Any] | None = None,
    ) -> RecordDetail:
        self.store.initialize()
        project_id = str(project_id)
        record = str(record)
        field_defs = normalize_field_definitions(field_definitions)
        value_rows = self._load_value_rows(project_id, record)
        values_by_field: dict[str, list[dict[str, Any]]] = {}
        for row in value_rows:
            values_by_field.setdefault(str(row["field_name"]), []).append(dict(row))

        sections: OrderedDict[str, list[RecordFieldValue]] = OrderedDict()
        consumed: set[tuple[str, str, str]] = set()

        for definition in field_defs:
            rows = values_by_field.get(definition.field_name, [])
            if not rows:
                sections.setdefault(definition.form_name, []).append(
                    RecordFieldValue(
                        field_name=definition.field_name,
                        value="",
                        form_name=definition.form_name,
                        field_label=definition.field_label,
                        field_type=definition.field_type,
                        present=False,
                    )
                )
                continue
            for row in rows:
                consumed.add(value_row_key(row))
                sections.setdefault(definition.form_name, []).append(
                    record_field_value_from_row(row, definition)
                )

        for row in value_rows:
            key = value_row_key(row)
            if key in consumed:
                continue
            fallback = FieldDefinition(
                field_name=str(row["field_name"]),
                form_name=UNKNOWN_FORM_NAME,
                field_label=str(row["field_name"]),
                field_type="",
            )
            sections.setdefault(UNKNOWN_FORM_NAME, []).append(
                record_field_value_from_row(row, fallback)
            )

        with self.store.connect() as db:
            state = db.execute(
                """
                SELECT dag_unique_name, remote_updated_at, local_updated_at, last_synced_at, dirty, conflict
                FROM record_sync_state
                WHERE project_id = ? AND record = ?
                """,
                (project_id, record),
            ).fetchone()
            hash_rows = db.execute(
                """
                SELECT tc_hash
                FROM identity_hash_map
                WHERE project_id = ? AND record = ?
                ORDER BY tc_hash
                """,
                (project_id, record),
            ).fetchall()
        return RecordDetail(
            project_id=project_id,
            record=record,
            dag_unique_name=optional_text(state["dag_unique_name"]) if state is not None else None,
            remote_updated_at=optional_text(state["remote_updated_at"]) if state is not None else None,
            local_updated_at=optional_text(state["local_updated_at"]) if state is not None else None,
            last_synced_at=optional_text(state["last_synced_at"]) if state is not None else None,
            dirty=bool(state["dirty"]) if state is not None else False,
            conflict=bool(state["conflict"]) if state is not None else False,
            identity_hashes=[str(row["tc_hash"]) for row in hash_rows],
            pending_changes=[
                item
                for item in self.store.pending_changes(project_id)
                if str(item.get("record")) == record
            ],
            forms=[
                RecordFormSection(form_name=form_name, fields=fields)
                for form_name, fields in sections.items()
            ],
        )

    def _load_value_rows(self, project_id: str, record: str) -> list[Any]:
        with self.store.connect() as db:
            return db.execute(
                """
                SELECT
                    project_id,
                    event_id,
                    record,
                    field_name,
                    value,
                    repeat_instrument,
                    instance,
                    dag_unique_name,
                    remote_updated_at,
                    local_updated_at,
                    source,
                    dirty
                FROM redcap_data_values
                WHERE project_id = ? AND record = ?
                ORDER BY event_id, instance, field_name
                """,
                (project_id, record),
            ).fetchall()


def apply_summary_labels(
    store: DataEntryStore,
    project_id: str,
    summaries: list[RecordSummary],
    label_fields: Iterable[str] | None,
) -> None:
    fields = [str(item) for item in (label_fields or []) if str(item)]
    if not summaries or not fields:
        return
    records = [item.record for item in summaries]
    placeholders = ",".join("?" for _ in records)
    field_placeholders = ",".join("?" for _ in fields)
    query = f"""
        SELECT record, field_name, value
        FROM redcap_data_values
        WHERE project_id = ?
          AND record IN ({placeholders})
          AND field_name IN ({field_placeholders})
          AND value != ''
        ORDER BY record, field_name
    """
    with store.connect() as db:
        rows = db.execute(query, [project_id, *records, *fields]).fetchall()
    values: dict[str, dict[str, str]] = {}
    for row in rows:
        values.setdefault(str(row["record"]), {})[str(row["field_name"])] = str(row["value"])
    for summary in summaries:
        label_parts = [
            values.get(summary.record, {}).get(field_name, "").strip()
            for field_name in fields
        ]
        label = " ".join(part for part in label_parts if part)
        if label:
            summary.label = label


def normalize_field_definitions(field_definitions: Iterable[Any] | None) -> list[FieldDefinition]:
    parsed: list[FieldDefinition] = []
    for item in field_definitions or []:
        field_name = optional_text(getattr(item, "field_name", None))
        if not field_name and isinstance(item, dict):
            field_name = optional_text(item.get("field_name"))
        if not field_name:
            continue
        form_name = optional_text(getattr(item, "form_name", None))
        field_label = optional_text(getattr(item, "field_label", None))
        field_type = optional_text(getattr(item, "field_type", None))
        if isinstance(item, dict):
            form_name = form_name or optional_text(item.get("form_name"))
            field_label = field_label or optional_text(item.get("field_label"))
            field_type = field_type or optional_text(item.get("field_type"))
        parsed.append(
            FieldDefinition(
                field_name=field_name,
                form_name=form_name or UNKNOWN_FORM_NAME,
                field_label=field_label or field_name,
                field_type=field_type or "",
            )
        )
    return parsed


def record_field_value_from_row(row: dict[str, Any], definition: FieldDefinition) -> RecordFieldValue:
    return RecordFieldValue(
        field_name=definition.field_name,
        value=str(row["value"]),
        event_id=normalize_key_part(row["event_id"]),
        instance=normalize_key_part(row["instance"]),
        repeat_instrument=normalize_key_part(row["repeat_instrument"]),
        form_name=definition.form_name,
        field_label=definition.field_label,
        field_type=definition.field_type,
        source=str(row["source"] or "remote"),
        dirty=bool(row["dirty"]),
        present=True,
        remote_updated_at=optional_text(row["remote_updated_at"]),
        local_updated_at=optional_text(row["local_updated_at"]),
    )


def value_row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        normalize_key_part(row["field_name"]),
        normalize_key_part(row["event_id"]),
        normalize_key_part(row["repeat_instrument"]),
        normalize_key_part(row["instance"]),
    )


def optional_text(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    return str(value)


def unique_non_empty(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        text = optional_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized
