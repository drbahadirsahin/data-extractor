import unittest

from data_entry_browser import RecordDetail, RecordFieldValue, RecordFormSection
from data_entry_form_model import (
    CHECKBOX_EDITOR,
    DATE_EDITOR,
    DESCRIPTION_EDITOR,
    DROPDOWN_EDITOR,
    DYNAMIC_DROPDOWN_EDITOR,
    RADIO_EDITOR,
    READONLY_EDITOR,
    TEXT_AREA_EDITOR,
    TEXT_EDITOR,
    build_form_render_model,
)
from dictionary_parser import FieldSpec


class DataEntryFormModelTests(unittest.TestCase):
    def test_builds_editor_models_from_redcap_field_metadata(self) -> None:
        detail = RecordDetail(
            project_id="17",
            record="1",
            dirty=True,
            forms=[
                RecordFormSection(
                    form_name="hasta_bilgileri",
                    fields=[
                        RecordFieldValue(field_name="hasta_ad", value="AB", dirty=True),
                        RecordFieldValue(field_name="notlar", value="long note"),
                        RecordFieldValue(field_name="evre", value="2"),
                        RecordFieldValue(field_name="yasiyor_mu", value="1"),
                        RecordFieldValue(field_name="risk___1", value="1"),
                        RecordFieldValue(field_name="risk___2", value="0"),
                    ],
                )
            ],
        )
        fields = {
            "hasta_bilgileri": [
                FieldSpec("hasta_ad", "hasta_bilgileri", "text", "Hasta adi"),
                FieldSpec("notlar", "hasta_bilgileri", "notes", "Notlar"),
                FieldSpec("evre", "hasta_bilgileri", "dropdown", "Evre", "1, T1 | 2, T2"),
                FieldSpec("yasiyor_mu", "hasta_bilgileri", "yesno", "Yasiyor mu"),
                FieldSpec("risk", "hasta_bilgileri", "checkbox", "Risk", "1, Sigara | 2, DM"),
            ]
        }

        model = build_form_render_model(detail, fields, form_labels={"hasta_bilgileri": "Hasta Bilgileri"})

        self.assertEqual(model.project_id, "17")
        self.assertEqual(model.record, "1")
        self.assertTrue(model.dirty)
        self.assertEqual(model.sections[0].title, "Hasta Bilgileri")
        by_name = {field.field_name: field for field in model.fields}
        self.assertEqual(by_name["hasta_ad"].editor, TEXT_EDITOR)
        self.assertEqual(by_name["hasta_ad"].value, "AB")
        self.assertTrue(by_name["hasta_ad"].dirty)
        self.assertEqual(by_name["notlar"].editor, TEXT_AREA_EDITOR)
        self.assertEqual(by_name["evre"].editor, DROPDOWN_EDITOR)
        self.assertEqual([(item.code, item.label) for item in by_name["evre"].choices], [("1", "T1"), ("2", "T2")])
        self.assertEqual(by_name["yasiyor_mu"].editor, RADIO_EDITOR)
        self.assertEqual([(item.code, item.label) for item in by_name["yasiyor_mu"].choices], [("1", "Evet"), ("0", "Hayir")])
        self.assertEqual(by_name["risk"].editor, CHECKBOX_EDITOR)
        self.assertEqual(by_name["risk"].value, ["1"])

    def test_marks_missing_metadata_fields_as_not_present(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {"form": [FieldSpec("missing", "form", "text", "Missing")]}

        model = build_form_render_model(detail, fields)

        self.assertFalse(model.fields[0].present)
        self.assertEqual(model.fields[0].value, "")

    def test_keeps_same_field_values_separate_by_event(self) -> None:
        detail = RecordDetail(
            project_id="17",
            record="96-6",
            forms=[
                RecordFormSection(
                    form_name="hasta_bilgileri",
                    fields=[
                        RecordFieldValue(
                            field_name="hasta_ad",
                            value="",
                            event_id="baseline_arm_1",
                            present=True,
                        ),
                        RecordFieldValue(
                            field_name="hasta_ad",
                            value="AH",
                            event_id="tbbi_bilgiler__tan_arm_1",
                            present=True,
                        ),
                    ],
                )
            ],
        )
        fields = {"hasta_bilgileri": [FieldSpec("hasta_ad", "hasta_bilgileri", "text", "Hasta adı")]}

        model = build_form_render_model(detail, fields)

        self.assertEqual([section.event_id for section in model.sections], ["baseline_arm_1", "tbbi_bilgiler__tan_arm_1"])
        self.assertEqual([section.fields[0].value for section in model.sections], ["", "AH"])
        self.assertEqual(model.sections[1].fields[0].context_key, "hasta_ad@@event=tbbi_bilgiler__tan_arm_1@@instance=")

    def test_uses_form_event_map_to_group_blank_forms_by_event(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {"hasta_bilgileri": [FieldSpec("hasta_ad", "hasta_bilgileri", "text", "Hasta adı")]}

        model = build_form_render_model(
            detail,
            fields,
            event_labels={"baseline_arm_1": "Başlangıç", "followup_arm_1": "İzlem"},
            form_event_map={"hasta_bilgileri": ["baseline_arm_1", "followup_arm_1"]},
        )

        self.assertEqual([section.event_id for section in model.sections], ["baseline_arm_1", "followup_arm_1"])
        self.assertEqual([section.event_label for section in model.sections], ["Başlangıç", "İzlem"])
        self.assertEqual([section.title for section in model.sections], ["hasta_bilgileri", "hasta_bilgileri"])
        self.assertEqual([section.fields[0].event_id for section in model.sections], ["baseline_arm_1", "followup_arm_1"])

    def test_maps_readonly_and_descriptive_fields(self) -> None:
        detail = RecordDetail(
            project_id="17",
            record="1",
            forms=[
                RecordFormSection(
                    form_name="form",
                    fields=[RecordFieldValue(field_name="score", value="12")],
                )
            ],
        )
        fields = {
            "form": [
                FieldSpec("score", "form", "calc", "Score"),
                FieldSpec("info", "form", "descriptive", "Read this text"),
            ]
        }

        model = build_form_render_model(detail, fields)

        self.assertEqual(model.fields[0].editor, READONLY_EDITOR)
        self.assertTrue(model.fields[0].read_only)
        self.assertEqual(model.fields[1].editor, DESCRIPTION_EDITOR)
        self.assertEqual(model.fields[1].value, "Read this text")

    def test_maps_date_and_dynamic_sql_fields(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "form": [
                FieldSpec("dogum_tarihi", "form", "text", "Doğum Tarihi", text_validation="date_ymd"),
                FieldSpec("mr_secimi", "form", "sql", "MR Seçimi"),
            ]
        }

        model = build_form_render_model(detail, fields)

        by_name = {field.field_name: field for field in model.fields}
        self.assertEqual(by_name["dogum_tarihi"].editor, DATE_EDITOR)
        self.assertEqual(by_name["mr_secimi"].editor, DYNAMIC_DROPDOWN_EDITOR)

    def test_hides_hidden_annotation_and_marks_readonly_annotation(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "form": [
                FieldSpec("secret", "form", "text", "Secret", field_annotation=["@HIDDEN"]),
                FieldSpec("locked", "form", "text", "Locked", field_annotation=["@READONLY"]),
                FieldSpec("visible", "form", "text", "Visible"),
            ]
        }

        model = build_form_render_model(detail, fields)
        by_name = {field.field_name: field for field in model.fields}

        self.assertNotIn("secret", by_name)
        self.assertTrue(by_name["locked"].read_only)
        self.assertIn("visible", by_name)

    def test_accepts_dict_metadata_with_required_and_branching_logic(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "form": [
                FieldSpec(
                    "x",
                    "form",
                    "text",
                    "X",
                    required="y",
                    branching_logic="[a] = '1'",
                    text_validation="integer",
                    text_validation_min="0",
                    text_validation_max="10",
                )
            ]
        }

        model = build_form_render_model(detail, fields)

        self.assertTrue(model.fields[0].required)
        self.assertEqual(model.fields[0].branching_logic, "[a] = '1'")
        self.assertEqual(model.fields[0].validation, "integer")
        self.assertEqual(model.fields[0].validation_min, "0")
        self.assertEqual(model.fields[0].validation_max, "10")


if __name__ == "__main__":
    unittest.main()
