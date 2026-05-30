from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from data_entry_store import DataEntryStore, RedcapDataValue, RemoteRecordManifest
from data_entry_sync_client import (
    IdentityHashMapResponse,
    RecordDataResponse,
    SyncManifestResponse,
)


class DataEntrySyncClientProtocol(Protocol):
    def get_sync_manifest(self, *, since: str | None = None) -> SyncManifestResponse:
        ...

    def get_record_data(
        self,
        *,
        records: Iterable[str] | None = None,
        fields: Iterable[str] | None = None,
        events: Iterable[str] | None = None,
        since: str | None = None,
    ) -> RecordDataResponse:
        ...

    def get_identity_hash_map(self, *, since: str | None = None) -> IdentityHashMapResponse:
        ...


@dataclass(frozen=True)
class DataEntrySyncReport:
    project_id: str | None
    manifest_records: int
    pulled_records: list[str] = field(default_factory=list)
    conflict_records: list[str] = field(default_factory=list)
    unchanged_records: list[str] = field(default_factory=list)
    values_updated: int = 0
    identity_hashes_updated: int = 0
    pending_changes: int = 0

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflict_records)


class DataEntrySyncService:
    def __init__(self, store: DataEntryStore, client: DataEntrySyncClientProtocol) -> None:
        self.store = store
        self.client = client

    def sync_read_only(
        self,
        *,
        since: str | None = None,
        fields: Iterable[str] | None = None,
        events: Iterable[str] | None = None,
    ) -> DataEntrySyncReport:
        """
        Pull server-side changes into the local cache without submitting local edits.

        Records with queued local edits are never overwritten here. They are returned
        as conflicts so the later data-entry UI can ask the user how to resolve them.
        """
        self.store.initialize()
        manifest = self.client.get_sync_manifest(since=since)
        delta = self.store.compare_remote_manifest(manifest.records)
        manifest_by_record = {str(item.record): item for item in manifest.records}
        pulled_manifest = manifest_items_for_records(manifest_by_record, delta.to_pull)

        values_updated = 0
        if delta.to_pull:
            self.store.upsert_remote_manifest(pulled_manifest)
            for record_batch in batched(delta.to_pull, 50):
                record_data = self.client.get_record_data(
                    records=record_batch,
                    fields=fields,
                    events=events,
                    since=since,
                )
                normalized_values = fill_missing_project_ids(
                    record_data.values,
                    fallback_project_id=manifest.project_id or record_data.project_id,
                    manifest_by_record=manifest_by_record,
                )
                self.store.upsert_remote_values(normalized_values)
                values_updated += len(normalized_values)

        identity_hash_map = self.client.get_identity_hash_map(since=since)
        self.store.upsert_identity_hashes(identity_hash_map.entries)

        project_id = resolve_project_id(manifest, identity_hash_map, pulled_manifest)
        if project_id and delta.conflicts:
            self.store.mark_record_conflicts(project_id=project_id, records=delta.conflicts)
        pending_changes = (
            len(self.store.pending_changes(project_id))
            if project_id
            else len(self.store.pending_changes())
        )

        return DataEntrySyncReport(
            project_id=project_id,
            manifest_records=len(manifest.records),
            pulled_records=list(delta.to_pull),
            conflict_records=list(delta.conflicts),
            unchanged_records=list(delta.unchanged),
            values_updated=values_updated,
            identity_hashes_updated=len(identity_hash_map.entries),
            pending_changes=pending_changes,
        )


def manifest_items_for_records(
    manifest_by_record: dict[str, RemoteRecordManifest],
    records: Iterable[str],
) -> list[RemoteRecordManifest]:
    return [manifest_by_record[record] for record in records if record in manifest_by_record]


def resolve_project_id(
    manifest: SyncManifestResponse,
    identity_hash_map: IdentityHashMapResponse,
    pulled_manifest: list[RemoteRecordManifest],
) -> str | None:
    if manifest.project_id:
        return manifest.project_id
    if identity_hash_map.project_id:
        return identity_hash_map.project_id
    for item in pulled_manifest or manifest.records:
        if item.project_id:
            return item.project_id
    return None


def batched(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def fill_missing_project_ids(
    values: list[RedcapDataValue],
    *,
    fallback_project_id: str | None,
    manifest_by_record: dict[str, RemoteRecordManifest],
) -> list[RedcapDataValue]:
    normalized: list[RedcapDataValue] = []
    for value in values:
        if value.project_id:
            normalized.append(value)
            continue
        record_manifest = manifest_by_record.get(str(value.record))
        project_id = (
            str(record_manifest.project_id)
            if record_manifest is not None and record_manifest.project_id
            else str(fallback_project_id or "")
        )
        normalized.append(
            RedcapDataValue(
                project_id=project_id,
                event_id=value.event_id,
                record=value.record,
                field_name=value.field_name,
                value=value.value,
                repeat_instrument=value.repeat_instrument,
                instance=value.instance,
                dag_unique_name=value.dag_unique_name or (record_manifest.dag_unique_name if record_manifest else None),
                remote_updated_at=value.remote_updated_at
                or (record_manifest.remote_updated_at if record_manifest else None),
            )
        )
    return normalized
