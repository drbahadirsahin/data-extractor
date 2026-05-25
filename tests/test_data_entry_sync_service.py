import tempfile
import unittest
from pathlib import Path

from data_entry_store import (
    DataEntryStore,
    IdentityHashEntry,
    RedcapDataValue,
    RemoteRecordManifest,
)
from data_entry_sync_client import (
    IdentityHashMapResponse,
    RecordDataResponse,
    SyncManifestResponse,
)
from data_entry_sync_service import DataEntrySyncService


class FakeSyncClient:
    def __init__(
        self,
        *,
        manifest: SyncManifestResponse,
        record_data: RecordDataResponse | None = None,
        identity_hash_map: IdentityHashMapResponse | None = None,
    ) -> None:
        self.manifest = manifest
        self.record_data = record_data or RecordDataResponse(project_id=None, values=[], raw={})
        self.identity_hash_map = identity_hash_map or IdentityHashMapResponse(project_id=None, entries=[], raw={})
        self.record_data_calls: list[dict[str, object]] = []
        self.manifest_since: str | None = None
        self.identity_since: str | None = None

    def get_sync_manifest(self, *, since: str | None = None) -> SyncManifestResponse:
        self.manifest_since = since
        return self.manifest

    def get_record_data(
        self,
        *,
        records=None,
        fields=None,
        events=None,
        since: str | None = None,
    ) -> RecordDataResponse:
        self.record_data_calls.append(
            {
                "records": list(records or []),
                "fields": list(fields or []),
                "events": list(events or []),
                "since": since,
            }
        )
        return self.record_data

    def get_identity_hash_map(self, *, since: str | None = None) -> IdentityHashMapResponse:
        self.identity_since = since
        return self.identity_hash_map


class DataEntrySyncServiceTests(unittest.TestCase):
    def test_initial_sync_pulls_records_and_identity_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name="marmara",
                    identity_hash_updated_at="2026-05-24T10:05:00Z",
                    records=[
                        RemoteRecordManifest(
                            project_id="17",
                            record="1",
                            remote_updated_at="2026-05-24T10:00:00Z",
                            dag_unique_name="marmara",
                        ),
                        RemoteRecordManifest(
                            project_id="17",
                            record="2",
                            remote_updated_at="2026-05-24T10:01:00Z",
                            dag_unique_name="marmara",
                        ),
                    ],
                    raw={},
                ),
                record_data=RecordDataResponse(
                    project_id="17",
                    values=[
                        RedcapDataValue(
                            project_id="17",
                            event_id="",
                            record="1",
                            field_name="hasta_ad",
                            value="AB",
                            dag_unique_name="marmara",
                            remote_updated_at="2026-05-24T10:00:00Z",
                        ),
                        RedcapDataValue(
                            project_id="17",
                            event_id="",
                            record="2",
                            field_name="hasta_ad",
                            value="CD",
                            dag_unique_name="marmara",
                            remote_updated_at="2026-05-24T10:01:00Z",
                        ),
                    ],
                    raw={},
                ),
                identity_hash_map=IdentityHashMapResponse(
                    project_id="17",
                    entries=[
                        IdentityHashEntry(project_id="17", tc_hash="hash-1", record="1"),
                        IdentityHashEntry(project_id="17", tc_hash="hash-2", record="2"),
                    ],
                    raw={},
                ),
            )

            report = DataEntrySyncService(store, client).sync_read_only()

            self.assertEqual(report.project_id, "17")
            self.assertEqual(report.pulled_records, ["1", "2"])
            self.assertEqual(report.values_updated, 2)
            self.assertEqual(report.identity_hashes_updated, 2)
            self.assertEqual(client.record_data_calls[0]["records"], ["1", "2"])
            self.assertEqual(store.lookup_record_by_tc_hash("17", "hash-2"), "2")
            self.assertEqual(len(store.redcap_data_rows("17")), 2)

    def test_unchanged_records_do_not_fetch_record_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    )
                ]
            )
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name=None,
                    identity_hash_updated_at=None,
                    records=[
                        RemoteRecordManifest(
                            project_id="17",
                            record="1",
                            remote_updated_at="2026-05-24T10:00:00Z",
                        )
                    ],
                    raw={},
                ),
            )

            report = DataEntrySyncService(store, client).sync_read_only()

            self.assertEqual(report.unchanged_records, ["1"])
            self.assertEqual(client.record_data_calls, [])

    def test_dirty_record_with_newer_server_manifest_becomes_conflict_without_pull(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    )
                ]
            )
            store.queue_local_change(
                project_id="17",
                record="1",
                field_name="hasta_ad",
                new_value="EF",
                base_remote_updated_at="2026-05-24T10:00:00Z",
            )
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name=None,
                    identity_hash_updated_at=None,
                    records=[
                        RemoteRecordManifest(
                            project_id="17",
                            record="1",
                            remote_updated_at="2026-05-24T11:00:00Z",
                        )
                    ],
                    raw={},
                ),
            )

            report = DataEntrySyncService(store, client).sync_read_only()

            self.assertEqual(report.conflict_records, ["1"])
            self.assertTrue(report.has_conflicts)
            self.assertEqual(report.pending_changes, 1)
            self.assertEqual(client.record_data_calls, [])
            self.assertEqual(store.redcap_data_rows("17", "1")[0]["value"], "EF")
            with store.connect() as db:
                row = db.execute(
                    "SELECT conflict FROM record_sync_state WHERE project_id = '17' AND record = '1'"
                ).fetchone()
            self.assertEqual(row["conflict"], 1)

    def test_clean_record_with_newer_server_manifest_is_pulled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    )
                ]
            )
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name="marmara",
                    identity_hash_updated_at=None,
                    records=[
                        RemoteRecordManifest(
                            project_id="17",
                            record="1",
                            remote_updated_at="2026-05-24T11:00:00Z",
                            dag_unique_name="marmara",
                        )
                    ],
                    raw={},
                ),
                record_data=RecordDataResponse(
                    project_id="17",
                    values=[
                        RedcapDataValue(
                            project_id="17",
                            event_id="",
                            record="1",
                            field_name="hasta_ad",
                            value="GH",
                            dag_unique_name="marmara",
                            remote_updated_at="2026-05-24T11:00:00Z",
                        )
                    ],
                    raw={},
                ),
            )

            report = DataEntrySyncService(store, client).sync_read_only()

            self.assertEqual(report.pulled_records, ["1"])
            self.assertEqual(report.values_updated, 1)
            self.assertEqual(store.redcap_data_rows("17", "1")[0]["value"], "GH")

    def test_empty_cached_record_is_pulled_again(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            manifest = SyncManifestResponse(
                project_id="17",
                dag_unique_name="marmara",
                identity_hash_updated_at=None,
                records=[
                    RemoteRecordManifest(
                        project_id="17",
                        record="empty",
                        remote_updated_at="2026-05-24T10:00:00Z",
                        dag_unique_name="marmara",
                    )
                ],
                raw={},
            )
            first_client = FakeSyncClient(manifest=manifest)

            first_report = DataEntrySyncService(store, first_client).sync_read_only()

            self.assertEqual(first_report.pulled_records, ["empty"])
            self.assertEqual(first_client.record_data_calls[0]["records"], ["empty"])

            second_client = FakeSyncClient(manifest=manifest)
            second_report = DataEntrySyncService(store, second_client).sync_read_only()

            self.assertEqual(second_report.pulled_records, ["empty"])
            self.assertEqual(second_client.record_data_calls[0]["records"], ["empty"])

    def test_sync_passes_since_to_all_remote_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name=None,
                    identity_hash_updated_at=None,
                    records=[
                        RemoteRecordManifest(
                            project_id="17",
                            record="1",
                            remote_updated_at="2026-05-24T10:00:00Z",
                        )
                    ],
                    raw={},
                )
            )

            DataEntrySyncService(store, client).sync_read_only(
                since="2026-05-23T00:00:00Z",
                fields=["hasta_ad"],
                events=["event_1_arm_1"],
            )

            self.assertEqual(client.manifest_since, "2026-05-23T00:00:00Z")
            self.assertEqual(client.identity_since, "2026-05-23T00:00:00Z")
            self.assertEqual(client.record_data_calls[0]["fields"], ["hasta_ad"])
            self.assertEqual(client.record_data_calls[0]["events"], ["event_1_arm_1"])

    def test_missing_project_ids_are_filled_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name="marmara",
                    identity_hash_updated_at=None,
                    records=[
                        RemoteRecordManifest(
                            project_id="17",
                            record="1",
                            remote_updated_at="2026-05-24T10:00:00Z",
                            dag_unique_name="marmara",
                        )
                    ],
                    raw={},
                ),
                record_data=RecordDataResponse(
                    project_id=None,
                    values=[
                        RedcapDataValue(
                            project_id="",
                            event_id="",
                            record="1",
                            field_name="hasta_ad",
                            value="AB",
                        )
                    ],
                    raw={},
                ),
            )

            report = DataEntrySyncService(store, client).sync_read_only()

            self.assertEqual(report.values_updated, 1)
            rows = store.redcap_data_rows("17", "1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["field_name"], "hasta_ad")
            self.assertEqual(rows[0]["value"], "AB")

    def test_large_initial_sync_fetches_record_data_in_batches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            manifests = [
                RemoteRecordManifest(
                    project_id="17",
                    record=str(index),
                    remote_updated_at="2026-05-24T10:00:00Z",
                )
                for index in range(125)
            ]
            client = FakeSyncClient(
                manifest=SyncManifestResponse(
                    project_id="17",
                    dag_unique_name=None,
                    identity_hash_updated_at=None,
                    records=manifests,
                    raw={},
                )
            )

            DataEntrySyncService(store, client).sync_read_only()

            self.assertEqual(len(client.record_data_calls), 3)
            self.assertEqual(len(client.record_data_calls[0]["records"]), 50)
            self.assertEqual(len(client.record_data_calls[1]["records"]), 50)
            self.assertEqual(len(client.record_data_calls[2]["records"]), 25)


if __name__ == "__main__":
    unittest.main()
