import tempfile
import unittest
from pathlib import Path

from data_entry_store import (
    DataEntryStore,
    IdentityHashEntry,
    RedcapDataValue,
    RemoteRecordManifest,
)


class DataEntryStoreTests(unittest.TestCase):
    def test_initialize_creates_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()

            self.assertEqual(store.schema_version(), 1)

            with store.connect() as db:
                row = db.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'view' AND name = 'redcap_data'"
                ).fetchone()
            self.assertIsNotNone(row)

    def test_identity_hash_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()

            store.upsert_identity_hashes(
                [
                    IdentityHashEntry(
                        project_id="17",
                        tc_hash="hash-1",
                        record="1001",
                        dag_unique_name="marmara",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    )
                ]
            )

            self.assertEqual(store.lookup_record_by_tc_hash("17", "hash-1"), "1001")
            self.assertIsNone(store.lookup_record_by_tc_hash("17", "missing"))

    def test_redcap_data_values_are_available_through_redcap_data_view(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()

            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id=None,
                        record="1",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id=None,
                        record="1",
                        field_name="hasta_soyad",
                        value="CD",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                ]
            )

            rows = store.redcap_data_rows("17", "1")
            self.assertEqual(
                [(row["field_name"], row["value"]) for row in rows],
                [("hasta_ad", "AB"), ("hasta_soyad", "CD")],
            )

            with store.connect() as db:
                view_rows = db.execute(
                    """
                    SELECT project_id, event_id, record, field_name, value, instance
                    FROM redcap_data
                    WHERE project_id = '17' AND record = '1'
                    ORDER BY field_name
                    """
                ).fetchall()
            self.assertEqual(view_rows[0]["field_name"], "hasta_ad")
            self.assertEqual(view_rows[0]["event_id"], "")
            self.assertEqual(view_rows[0]["instance"], "")

    def test_queue_local_change_marks_record_dirty_and_pending(self) -> None:
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

            change_id = store.queue_local_change(
                project_id="17",
                record="1",
                field_name="hasta_ad",
                new_value="EF",
                base_remote_updated_at="2026-05-24T10:00:00Z",
            )

            self.assertGreater(change_id, 0)
            pending = store.pending_changes("17")
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["old_value"], "AB")
            self.assertEqual(pending[0]["new_value"], "EF")

            rows = store.redcap_data_rows("17", "1")
            self.assertEqual(rows[0]["value"], "EF")

            with store.connect() as db:
                state = db.execute(
                    "SELECT dirty FROM record_sync_state WHERE project_id = '17' AND record = '1'"
                ).fetchone()
            self.assertEqual(state["dirty"], 1)

    def test_compare_remote_manifest_detects_pull_and_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="clean",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="dirty",
                        field_name="hasta_ad",
                        value="CD",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="same",
                        field_name="hasta_ad",
                        value="EF",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                ]
            )
            store.queue_local_change(
                project_id="17",
                record="dirty",
                field_name="hasta_ad",
                new_value="GH",
                base_remote_updated_at="2026-05-24T10:00:00Z",
            )

            delta = store.compare_remote_manifest(
                [
                    RemoteRecordManifest(
                        project_id="17",
                        record="clean",
                        remote_updated_at="2026-05-24T11:00:00Z",
                    ),
                    RemoteRecordManifest(
                        project_id="17",
                        record="dirty",
                        remote_updated_at="2026-05-24T11:00:00Z",
                    ),
                    RemoteRecordManifest(
                        project_id="17",
                        record="same",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RemoteRecordManifest(
                        project_id="17",
                        record="new",
                        remote_updated_at="2026-05-24T11:00:00Z",
                    ),
                ]
            )

            self.assertEqual(delta.to_pull, ["clean", "new"])
            self.assertEqual(delta.conflicts, ["dirty"])
            self.assertEqual(delta.unchanged, ["same"])


if __name__ == "__main__":
    unittest.main()
