import tempfile
import unittest
from pathlib import Path

from data_entry_browser import DataEntryRecordBrowser
from data_entry_form_changes import apply_form_changes, build_form_change_set
from data_entry_form_model import (
    FormChoiceModel,
    FormFieldModel,
    FormRenderModel,
    FormSectionModel,
)
from data_entry_store import DataEntryStore, RedcapDataValue


class DataEntryFormChangesTests(unittest.TestCase):
    def test_build_change_set_detects_changed_scalar_values_only(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="form",
                    title="Form",
                    fields=[
                        FormFieldModel("hasta_ad", "form", "Hasta adi", "text", "AB"),
                        FormFieldModel("hasta_soyad", "form", "Hasta soyad", "text", "CD"),
                        FormFieldModel("score", "form", "Score", "readonly", "12", read_only=True),
                    ],
                )
            ],
        )

        change_set = build_form_change_set(
            model,
            {
                "hasta_ad": "EF",
                "hasta_soyad": "CD",
                "score": "99",
            },
        )

        self.assertEqual(len(change_set.changes), 1)
        self.assertEqual(change_set.changes[0].field_name, "hasta_ad")
        self.assertEqual(change_set.changes[0].old_value, "AB")
        self.assertEqual(change_set.changes[0].new_value, "EF")
        self.assertEqual(change_set.unchanged_count, 1)
        self.assertEqual(change_set.skipped_readonly_count, 1)

    def test_number_fields_compare_decimal_comma_and_dot_as_same_value(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="form",
                    title="Form",
                    fields=[
                        FormFieldModel(
                            "psa",
                            "form",
                            "PSA",
                            "text",
                            "14.46",
                            validation="number",
                        )
                    ],
                )
            ],
        )

        change_set = build_form_change_set(model, {"psa": "14,46"})

        self.assertEqual(change_set.changes, [])
        self.assertEqual(change_set.unchanged_count, 1)

    def test_number_field_changes_are_queued_with_dot_decimal_value(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="form",
                    title="Form",
                    fields=[
                        FormFieldModel(
                            "psa",
                            "form",
                            "PSA",
                            "text",
                            "14.46",
                            validation="number",
                        )
                    ],
                )
            ],
        )

        change_set = build_form_change_set(model, {"psa": "15,20"})

        self.assertEqual(len(change_set.changes), 1)
        self.assertEqual(change_set.changes[0].old_value, "14.46")
        self.assertEqual(change_set.changes[0].new_value, "15.20")

    def test_scientific_number_values_are_compared_as_plain_decimal_values(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="form",
                    title="Form",
                    fields=[
                        FormFieldModel(
                            "hasta_boy",
                            "form",
                            "Boy",
                            "text",
                            "1,425E+03",
                            validation="number",
                        )
                    ],
                )
            ],
        )

        change_set = build_form_change_set(model, {"hasta_boy": "1425"})

        self.assertEqual(change_set.changes, [])
        self.assertEqual(change_set.unchanged_count, 1)

    def test_build_change_set_expands_checkbox_choices_to_redcap_fields(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="form",
                    title="Form",
                    fields=[
                        FormFieldModel(
                            "risk",
                            "form",
                            "Risk",
                            "checkbox",
                            ["1"],
                            choices=[
                                FormChoiceModel("1", "Smoking"),
                                FormChoiceModel("2", "Diabetes"),
                            ],
                        )
                    ],
                )
            ],
        )

        change_set = build_form_change_set(
            model,
            {
                "risk___1": "0",
                "risk___2": "1",
            },
        )

        self.assertEqual([(item.field_name, item.old_value, item.new_value) for item in change_set.changes], [
            ("risk___1", "1", "0"),
            ("risk___2", "0", "1"),
        ])

    def test_apply_form_changes_queues_pending_changes_and_updates_local_values(self) -> None:
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
                    ),
                    RedcapDataValue(
                        project_id="17",
                        event_id="",
                        record="1",
                        field_name="risk___1",
                        value="1",
                        remote_updated_at="2026-05-24T10:00:00Z",
                    ),
                ]
            )
            model = FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel("hasta_ad", "form", "Hasta adi", "text", "AB"),
                            FormFieldModel(
                                "risk",
                                "form",
                                "Risk",
                                "checkbox",
                                ["1"],
                                choices=[FormChoiceModel("1", "Smoking")],
                            ),
                        ],
                    )
                ],
            )

            result = apply_form_changes(store, model, {"hasta_ad": "EF", "risk___1": "0"})

            self.assertEqual(result.queued_count, 2)
            pending = store.pending_changes("17")
            self.assertEqual([item["field_name"] for item in pending], ["hasta_ad", "risk___1"])
            rows = store.redcap_data_rows("17", "1")
            self.assertEqual({row["field_name"]: row["value"] for row in rows}, {
                "hasta_ad": "EF",
                "risk___1": "0",
            })
            self.assertTrue(DataEntryRecordBrowser(store).get_record_detail("17", "1").dirty)

    def test_apply_form_changes_skips_unchanged_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            model = FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[FormFieldModel("hasta_ad", "form", "Hasta adi", "text", "AB")],
                    )
                ],
            )

            result = apply_form_changes(store, model, {"hasta_ad": "AB"})

            self.assertEqual(result.queued_count, 0)
            self.assertEqual(store.pending_changes("17"), [])

    def test_build_change_set_preserves_event_context_for_duplicate_fields(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="form",
                    title="Baseline - Form",
                    event_id="baseline_arm_1",
                    fields=[
                        FormFieldModel(
                            "hasta_ad",
                            "form",
                            "Hasta adi",
                            "text",
                            "AB",
                            event_id="baseline_arm_1",
                            context_key="hasta_ad@@event=baseline_arm_1@@repeat=@@instance=",
                        )
                    ],
                ),
                FormSectionModel(
                    form_name="form",
                    title="Followup - Form",
                    event_id="followup_arm_1",
                    fields=[
                        FormFieldModel(
                            "hasta_ad",
                            "form",
                            "Hasta adi",
                            "text",
                            "CD",
                            event_id="followup_arm_1",
                            context_key="hasta_ad@@event=followup_arm_1@@repeat=@@instance=",
                        )
                    ],
                ),
            ],
        )

        change_set = build_form_change_set(
            model,
            {
                "hasta_ad@@event=baseline_arm_1@@repeat=@@instance=": "AB",
                "hasta_ad@@event=followup_arm_1@@repeat=@@instance=": "EF",
            },
        )

        self.assertEqual(len(change_set.changes), 1)
        self.assertEqual(change_set.changes[0].field_name, "hasta_ad")
        self.assertEqual(change_set.changes[0].event_id, "followup_arm_1")
        self.assertEqual(change_set.changes[0].new_value, "EF")


if __name__ == "__main__":
    unittest.main()
