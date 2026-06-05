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
        self.assertEqual(
            model.sections[1].fields[0].context_key,
            "hasta_ad@@event=tbbi_bilgiler__tan_arm_1@@repeat=@@instance=",
        )

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

    def test_form_event_map_is_authoritative_when_values_appear_in_other_events(self) -> None:
        detail = RecordDetail(
            project_id="17",
            record="1",
            forms=[
                RecordFormSection(
                    form_name="records",
                    fields=[
                        RecordFieldValue(field_name="hasta_ad", value="AB", event_id="wrong_event_arm_1"),
                        RecordFieldValue(field_name="hasta_ad", value="CD", event_id="tbbi_bilgiler__tan_arm_1"),
                        RecordFieldValue(field_name="psa", value="12", event_id="tbbi_bilgiler__tan_arm_1"),
                        RecordFieldValue(field_name="psa", value="8", event_id="tan_laboratuvar_arm_1"),
                    ],
                )
            ],
        )
        fields = {
            "hasta_bilgileri": [FieldSpec("hasta_ad", "hasta_bilgileri", "text", "Hasta adı")],
            "tan_laboratuvar_sonucu": [FieldSpec("psa", "tan_laboratuvar_sonucu", "text", "PSA")],
        }

        model = build_form_render_model(
            detail,
            fields,
            form_event_map={
                "hasta_bilgileri": ["tbbi_bilgiler__tan_arm_1"],
                "tan_laboratuvar_sonucu": ["tan_laboratuvar_arm_1"],
            },
        )

        self.assertEqual(
            [(section.event_id, section.form_name, section.fields[0].value) for section in model.sections],
            [
                ("tbbi_bilgiler__tan_arm_1", "hasta_bilgileri", "CD"),
                ("tan_laboratuvar_arm_1", "tan_laboratuvar_sonucu", "8"),
            ],
        )

    def test_instances_are_used_only_for_repeating_forms_or_events(self) -> None:
        detail = RecordDetail(
            project_id="17",
            record="1",
            forms=[
                RecordFormSection(
                    form_name="records",
                    fields=[
                        RecordFieldValue(field_name="static_value", value="A", event_id="event_1", instance="1"),
                        RecordFieldValue(
                            field_name="repeat_value",
                            value="B",
                            event_id="event_1",
                            repeat_instrument="repeat_form",
                            instance="1",
                        ),
                        RecordFieldValue(field_name="event_repeat", value="C", event_id="event_2", instance="1"),
                    ],
                )
            ],
        )
        fields = {
            "static_form": [FieldSpec("static_value", "static_form", "text", "Static")],
            "repeat_form": [FieldSpec("repeat_value", "repeat_form", "text", "Repeat")],
            "event_repeat_form": [FieldSpec("event_repeat", "event_repeat_form", "text", "Event Repeat")],
        }

        model = build_form_render_model(
            detail,
            fields,
            form_event_map={
                "static_form": ["event_1"],
                "repeat_form": ["event_1"],
                "event_repeat_form": ["event_2"],
            },
            repeating_forms=["repeat_form"],
            repeating_events=["event_2"],
        )

        self.assertEqual(
            [(section.form_name, section.event_id, section.instance) for section in model.sections],
            [
                ("static_form", "event_1", ""),
                ("repeat_form", "event_1", "1"),
                ("event_repeat_form", "event_2", "1"),
            ],
        )

    def test_empty_repeating_event_still_renders_first_instance_for_entry(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "event_repeat_form": [FieldSpec("event_repeat", "event_repeat_form", "text", "Event Repeat")],
        }

        model = build_form_render_model(
            detail,
            fields,
            form_event_map={"event_repeat_form": ["event_2"]},
            repeating_events=["event_2"],
        )

        self.assertEqual(len(model.sections), 1)
        self.assertEqual(model.sections[0].form_name, "event_repeat_form")
        self.assertEqual(model.sections[0].event_id, "event_2")
        self.assertEqual(model.sections[0].instance, "1")
        self.assertEqual(model.sections[0].fields[0].event_id, "event_2")
        self.assertEqual(model.sections[0].fields[0].instance, "1")

    def test_form_repeating_inside_empty_repeating_event_renders_first_form_instance(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "mr_trus_fzyon_biyopsi": [
                FieldSpec("mr_trus_bx_tarihi", "mr_trus_fzyon_biyopsi", "text", "Tarih"),
            ],
        }

        model = build_form_render_model(
            detail,
            fields,
            form_event_map={"mr_trus_fzyon_biyopsi": ["mr_trus_fzyon_biyopsi_arm_1"]},
            repeating_form_event_map={"mr_trus_fzyon_biyopsi": ["mr_trus_fzyon_biyopsi_arm_1"]},
            repeating_events=["mr_trus_fzyon_biyopsi_arm_1"],
        )

        self.assertEqual(len(model.sections), 1)
        section = model.sections[0]
        self.assertEqual(section.form_name, "mr_trus_fzyon_biyopsi")
        self.assertEqual(section.event_id, "mr_trus_fzyon_biyopsi_arm_1")
        self.assertEqual(section.repeat_instrument, "mr_trus_fzyon_biyopsi")
        self.assertEqual(section.instance, "1")
        self.assertEqual(section.fields[0].repeat_instrument, "mr_trus_fzyon_biyopsi")
        self.assertEqual(section.fields[0].instance, "1")

    def test_repeating_form_instances_do_not_create_blank_sibling_instances(self) -> None:
        detail = RecordDetail(
            project_id="17",
            record="1",
            forms=[
                RecordFormSection(
                    form_name="records",
                    fields=[
                        RecordFieldValue(
                            field_name="lab_psa",
                            value="4.2",
                            event_id="event_1",
                            repeat_instrument="tan_laboratuvar_sonucu",
                            instance="1",
                        ),
                        RecordFieldValue(
                            field_name="lab_psa",
                            value="5.1",
                            event_id="event_1",
                            repeat_instrument="tan_laboratuvar_sonucu",
                            instance="2",
                        ),
                        RecordFieldValue(
                            field_name="aile_kanser",
                            value="",
                            event_id="event_1",
                            repeat_instrument="tan_laboratuvar_sonucu",
                            instance="1",
                        ),
                        RecordFieldValue(
                            field_name="aile_kanser",
                            value="",
                            event_id="event_1",
                            repeat_instrument="tan_laboratuvar_sonucu",
                            instance="2",
                        ),
                    ],
                )
            ],
        )
        fields = {
            "ailede_dier_kanser_yks": [FieldSpec("aile_kanser", "ailede_dier_kanser_yks", "text", "Kanser")],
            "tan_laboratuvar_sonucu": [FieldSpec("lab_psa", "tan_laboratuvar_sonucu", "text", "PSA")],
        }

        model = build_form_render_model(
            detail,
            fields,
            form_event_map={
                "ailede_dier_kanser_yks": ["event_1"],
                "tan_laboratuvar_sonucu": ["event_1"],
            },
            repeating_form_event_map={
                "ailede_dier_kanser_yks": ["event_1"],
                "tan_laboratuvar_sonucu": ["event_1"],
            },
        )

        self.assertEqual(
            [(section.form_name, section.repeat_instrument, section.instance) for section in model.sections],
            [
                ("tan_laboratuvar_sonucu", "tan_laboratuvar_sonucu", "1"),
                ("tan_laboratuvar_sonucu", "tan_laboratuvar_sonucu", "2"),
            ],
        )

    def test_additional_repeat_contexts_create_blank_sections_on_demand(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "tan_laboratuvar_sonucu": [FieldSpec("psa", "tan_laboratuvar_sonucu", "text", "PSA")],
        }

        model = build_form_render_model(
            detail,
            fields,
            form_event_map={"tan_laboratuvar_sonucu": ["event_1"]},
            repeating_form_event_map={"tan_laboratuvar_sonucu": ["event_1"]},
            additional_contexts_by_form={
                "tan_laboratuvar_sonucu": [("event_1", "tan_laboratuvar_sonucu", "1")]
            },
        )

        self.assertEqual(len(model.sections), 1)
        self.assertEqual(model.sections[0].event_id, "event_1")
        self.assertEqual(model.sections[0].repeat_instrument, "tan_laboratuvar_sonucu")
        self.assertEqual(model.sections[0].instance, "1")
        self.assertFalse(model.sections[0].fields[0].present)

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
        self.assertIsNone(model.fields[0].calc_expression)
        self.assertEqual(model.fields[1].editor, DESCRIPTION_EDITOR)
        self.assertEqual(model.fields[1].value, "Read this text")

    def test_preserves_calc_expression_for_live_form_calculation(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        fields = {
            "form": [
                FieldSpec("kilo", "form", "text", "Kilo"),
                FieldSpec("boy", "form", "text", "Boy"),
                FieldSpec("vki", "form", "calc", "VKİ", "round(([kilo]*10000)/([boy]*[boy]),2)"),
            ]
        }

        model = build_form_render_model(detail, fields)
        by_name = {field.field_name: field for field in model.fields}

        self.assertEqual(by_name["vki"].editor, READONLY_EDITOR)
        self.assertEqual(by_name["vki"].calc_expression, "round(([kilo]*10000)/([boy]*[boy]),2)")

    def test_maps_date_and_dynamic_sql_fields(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        sql = "select value from redcap_data where project_id=17 and record=[record-name]"
        fields = {
            "form": [
                FieldSpec("dogum_tarihi", "form", "text", "Doğum Tarihi", text_validation="date_ymd"),
                FieldSpec("mr_secimi", "form", "sql", "MR Seçimi", sql),
            ]
        }

        model = build_form_render_model(detail, fields)

        by_name = {field.field_name: field for field in model.fields}
        self.assertEqual(by_name["dogum_tarihi"].editor, DATE_EDITOR)
        self.assertEqual(by_name["mr_secimi"].editor, DYNAMIC_DROPDOWN_EDITOR)
        self.assertEqual(by_name["mr_secimi"].dynamic_sql, sql)
        self.assertEqual(by_name["mr_secimi"].choices, [])

    def test_dynamic_sql_fields_use_provider_options_instead_of_query_text(self) -> None:
        detail = RecordDetail(project_id="17", record="1")
        sql = "select value from redcap_data where project_id=17 and record=[record-name]"
        fields = {"form": [FieldSpec("mr_secimi", "form", "sql", "MR Seçimi", sql)]}

        model = build_form_render_model(
            detail,
            fields,
            dynamic_options_provider=lambda field_spec, record: [
                {"code": "2026-05-28", "label": "MR Tarihi: 2026-05-28"}
            ],
        )

        field = model.fields[0]
        self.assertEqual(field.editor, DYNAMIC_DROPDOWN_EDITOR)
        self.assertEqual([(item.code, item.label) for item in field.choices], [
            ("2026-05-28", "MR Tarihi: 2026-05-28")
        ])
        self.assertNotIn("select", field.choices[0].label.lower())

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
