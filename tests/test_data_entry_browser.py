import tempfile
import unittest
from pathlib import Path

from data_entry_browser import (
    UNKNOWN_FORM_NAME,
    DataEntryRecordBrowser,
    FieldDefinition,
)
from data_entry_store import (
    DataEntryStore,
    IdentityHashEntry,
    RedcapDataValue,
    RemoteRecordManifest,
)


class DataEntryRecordBrowserTests(unittest.TestCase):
    def test_list_records_returns_status_counts_and_optional_labels(self) -> None:
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
                        dag_unique_name="marmara",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="hasta_soyad",
                        value="CD",
                        dag_unique_name="marmara",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                ]
            )
            store.upsert_identity_hashes(
                [
                    IdentityHashEntry(
                        project_id="17",
                        tc_hash="hash-1",
                        record="1",
                        dag_unique_name="marmara",
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

            records = DataEntryRecordBrowser(store).list_records(
                "17",
                label_fields=["hasta_ad", "hasta_soyad"],
            )

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].record, "1")
            self.assertEqual(records[0].label, "EF CD")
            self.assertEqual(records[0].dag_unique_name, "marmara")
            self.assertTrue(records[0].dirty)
            self.assertEqual(records[0].value_count, 2)
            self.assertEqual(records[0].identity_hash_count, 1)
            self.assertEqual(records[0].pending_change_count, 1)

    def test_list_records_searches_values_hashes_and_record_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="alpha",
                        field_name="hasta_ad",
                        value="Ayse",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="beta",
                        field_name="hasta_ad",
                        value="Mehmet",
                    ),
                ]
            )
            store.upsert_identity_hashes(
                [IdentityHashEntry(project_id="17", tc_hash="tc-hash-beta", record="beta")]
            )
            browser = DataEntryRecordBrowser(store)

            self.assertEqual([item.record for item in browser.list_records("17", search="Ayse")], ["alpha"])
            self.assertEqual([item.record for item in browser.list_records("17", search="hash-beta")], ["beta"])
            self.assertEqual([item.record for item in browser.list_records("17", search="alp")], ["alpha"])

    def test_get_record_detail_groups_metadata_fields_and_keeps_empty_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="17",
                        event_id="event_1",
                        record="1",
                        field_name="hasta_ad",
                        value="AB",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="event_1",
                        record="1",
                        field_name="unknown_field",
                        value="extra",
                    ),
                ]
            )
            store.upsert_identity_hashes(
                [IdentityHashEntry(project_id="17", tc_hash="hash-1", record="1")]
            )
            detail = DataEntryRecordBrowser(store).get_record_detail(
                "17",
                "1",
                field_definitions=[
                    FieldDefinition(
                        field_name="hasta_ad",
                        form_name="hasta_bilgileri",
                        field_label="Hasta adı",
                        field_type="text",
                    ),
                    FieldDefinition(
                        field_name="hasta_soyad",
                        form_name="hasta_bilgileri",
                        field_label="Hasta soyadı",
                        field_type="text",
                    ),
                ],
            )

            self.assertEqual(detail.record, "1")
            self.assertEqual(detail.identity_hashes, ["hash-1"])
            self.assertEqual([section.form_name for section in detail.forms], ["hasta_bilgileri", UNKNOWN_FORM_NAME])
            known_values = detail.forms[0].fields
            self.assertEqual([(item.field_name, item.value, item.present) for item in known_values], [
                ("hasta_ad", "AB", True),
                ("hasta_soyad", "", False),
            ])
            self.assertEqual(detail.forms[1].fields[0].field_name, "unknown_field")
            self.assertEqual(detail.forms[1].fields[0].value, "extra")

    def test_get_record_detail_reports_conflicts_and_pending_changes(self) -> None:
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
                new_value="CD",
                base_remote_updated_at="2026-05-24T10:00:00Z",
            )
            store.mark_record_conflicts(project_id="17", records=["1"])

            detail = DataEntryRecordBrowser(store).get_record_detail("17", "1")

            self.assertTrue(detail.dirty)
            self.assertTrue(detail.conflict)
            self.assertEqual(len(detail.pending_changes), 1)
            self.assertEqual(detail.field_values[0].value, "CD")

    def test_list_records_includes_manifest_only_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_manifest(
                [
                    RemoteRecordManifest(
                        project_id="17",
                        record="manifest-only",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    )
                ]
            )

            records = DataEntryRecordBrowser(store).list_records("17")

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].record, "manifest-only")
            self.assertEqual(records[0].value_count, 0)


if __name__ == "__main__":
    unittest.main()
