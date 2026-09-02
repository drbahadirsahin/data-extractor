import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data_entry_form_model import FormFieldModel, FormRenderModel, FormSectionModel
from gui.data_entry_record_matrix import (
    MATRIX_STATUS_EMPTY,
    MATRIX_STATUS_FILLED,
    MATRIX_STATUS_INCOMPLETE,
    MATRIX_STATUS_PARTIAL,
    MATRIX_STATUS_UNVERIFIED,
    DataEntryRecordMatrix,
    build_record_matrix,
)


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def record_model() -> FormRenderModel:
    return FormRenderModel(
        project_id="17",
        record="96-3",
        title="96-3 Ahmet Yılmaz",
        sections=[
            FormSectionModel(
                form_name="hasta_bilgileri",
                title="Hasta Bilgileri",
                event_id="tibbi_bilgiler_arm_1",
                event_label="Tıbbi Bilgiler & Tanı",
                fields=[
                    FormFieldModel("hasta_ad", "hasta_bilgileri", "Ad", "text", "Ahmet", required=True),
                    FormFieldModel("hasta_soyad", "hasta_bilgileri", "Soyad", "text", "", required=True),
                ],
            ),
            FormSectionModel(
                form_name="tan_laboratuvar_sonucu",
                title="Tanı Laboratuvar Sonucu",
                event_id="tibbi_bilgiler_arm_1",
                event_label="Tıbbi Bilgiler & Tanı",
                repeat_instrument="tan_laboratuvar_sonucu",
                instance="1",
                fields=[
                    FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "4.2", required=True),
                ],
            ),
            FormSectionModel(
                form_name="tan_laboratuvar_sonucu",
                title="Tanı Laboratuvar Sonucu",
                event_id="tibbi_bilgiler_arm_1",
                event_label="Tıbbi Bilgiler & Tanı",
                repeat_instrument="tan_laboratuvar_sonucu",
                instance="2",
                fields=[
                    FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "", required=True),
                ],
            ),
            FormSectionModel(
                form_name="klasik_biyopsi",
                title="Klasik Biyopsi",
                event_id="klasik_biyopsi_arm_1",
                event_label="Klasik Biyopsi  #1",
                instance="1",
                fields=[
                    FormFieldModel("bx_tarih", "klasik_biyopsi", "Tarih", "text", "2026-05-10"),
                ],
            ),
            FormSectionModel(
                form_name="klasik_biyopsi",
                title="Klasik Biyopsi",
                event_id="klasik_biyopsi_arm_1",
                event_label="Klasik Biyopsi  #2",
                instance="2",
                fields=[
                    FormFieldModel("bx_tarih", "klasik_biyopsi", "Tarih", "text", ""),
                ],
            ),
        ],
    )


def repeat_actions():
    return [
        {
            "kind": "event",
            "event_id": "klasik_biyopsi_arm_1",
            "event_label": "Klasik Biyopsi",
            "label": "Event: Klasik Biyopsi #3",
        },
        {
            "kind": "form",
            "form_name": "tan_laboratuvar_sonucu",
            "event_id": "tibbi_bilgiler_arm_1",
            "label": "Form: Tıbbi Bilgiler & Tanı / Tanı Laboratuvar Sonucu #3",
        },
    ]


class DataEntryRecordMatrixModelTests(unittest.TestCase):
    def test_maps_event_instances_to_columns_and_instruments_to_rows(self) -> None:
        matrix = build_record_matrix(record_model(), repeat_actions())

        self.assertEqual(
            [column.key for column in matrix.columns],
            [
                ("tibbi_bilgiler_arm_1", ""),
                ("klasik_biyopsi_arm_1", "1"),
                ("klasik_biyopsi_arm_1", "2"),
            ],
        )
        self.assertEqual(
            [row.form_name for row in matrix.rows],
            ["hasta_bilgileri", "tan_laboratuvar_sonucu", "klasik_biyopsi"],
        )

        repeat_cell = matrix.cell("tan_laboratuvar_sonucu", ("tibbi_bilgiler_arm_1", ""))
        self.assertEqual([target.instance for target in repeat_cell.targets], ["1", "2"])
        self.assertEqual([target.section_index for target in repeat_cell.targets], [1, 2])
        self.assertEqual([action["kind"] for action in repeat_cell.repeat_actions], ["form"])

    def test_places_new_event_on_latest_event_column(self) -> None:
        matrix = build_record_matrix(record_model(), repeat_actions())

        first_event = next(column for column in matrix.columns if column.key == ("klasik_biyopsi_arm_1", "1"))
        latest_event = next(column for column in matrix.columns if column.key == ("klasik_biyopsi_arm_1", "2"))

        self.assertEqual(first_event.repeat_actions, [])
        self.assertEqual([action["kind"] for action in latest_event.repeat_actions], ["event"])

    def test_keeps_repeat_instrument_instances_and_add_action_in_event_form_cell(self) -> None:
        matrix = build_record_matrix(record_model(), repeat_actions())

        cell = matrix.cell("tan_laboratuvar_sonucu", ("tibbi_bilgiler_arm_1", ""))
        self.assertEqual([target.instance for target in cell.targets], ["1", "2"])
        self.assertEqual([action["kind"] for action in cell.repeat_actions], ["form"])
        self.assertEqual(matrix.repeat_cards, [])

    def test_keeps_explicit_blank_repeat_draft_visible_as_an_instance(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="96-3",
            title="96-3",
            sections=[
                FormSectionModel(
                    form_name="multiparametrik_mr",
                    title="Multiparametrik MR",
                    event_id="mr_arm_1",
                    event_label="Multiparametrik MR",
                    repeat_instrument="multiparametrik_mr",
                    instance="1",
                    fields=[
                        FormFieldModel(
                            "mr_tarih",
                            "multiparametrik_mr",
                            "MR tarihi",
                            "text",
                            "",
                            present=False,
                        )
                    ],
                )
            ],
        )
        action = {
            "kind": "form",
            "form_name": "multiparametrik_mr",
            "event_id": "mr_arm_1",
            "label": "Form: Multiparametrik MR #1",
        }

        matrix = build_record_matrix(model, [action])

        cell = matrix.cell("multiparametrik_mr", ("mr_arm_1", ""))
        self.assertEqual([target.instance for target in cell.targets], ["1"])
        self.assertEqual(cell.targets[0].status, MATRIX_STATUS_EMPTY)
        self.assertEqual(cell.repeat_actions, [action])
        self.assertEqual(matrix.repeat_cards, [])

    def test_keeps_explicit_blank_repeating_event_draft_as_event_one(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="96-3",
            title="96-3",
            sections=[
                FormSectionModel(
                    form_name="klasik_biyopsi",
                    title="Klasik Biyopsi",
                    event_id="klasik_biyopsi_arm_1",
                    event_label="Klasik Biyopsi #1",
                    instance="1",
                    fields=[
                        FormFieldModel(
                            "bx_tarih",
                            "klasik_biyopsi",
                            "Tarih",
                            "text",
                            "",
                            present=False,
                        )
                    ],
                )
            ],
        )
        action = {
            "kind": "event",
            "event_id": "klasik_biyopsi_arm_1",
            "label": "Event: Klasik Biyopsi #1",
        }

        matrix = build_record_matrix(model, [action])

        self.assertEqual([column.key for column in matrix.columns], [("klasik_biyopsi_arm_1", "1")])
        self.assertEqual(matrix.columns[0].label, "Klasik Biyopsi #1")
        self.assertEqual(matrix.columns[0].repeat_actions, [action])
        self.assertEqual(
            [target.instance for target in matrix.cell("klasik_biyopsi", matrix.columns[0].key).targets],
            ["1"],
        )

    def test_actions_create_empty_event_columns_and_inline_form_cells_without_phantom_sections(self) -> None:
        model = FormRenderModel(project_id="17", record="96-3", title="96-3", sections=[])
        actions = [
            {
                "kind": "event",
                "event_id": "followup_arm_1",
                "event_label": "İzlem",
                "form_labels": {"takip": "Tedavi Sonrası İzlem"},
                "label": "Event: İzlem #1",
            },
            {
                "kind": "form",
                "form_name": "multiparametrik_mr",
                "form_label": "Multiparametrik MR",
                "event_id": "baseline_arm_1",
                "event_label": "Tıbbi Bilgiler & Tanı",
                "label": "Form: Multiparametrik MR #1",
            },
        ]

        matrix = build_record_matrix(model, actions)

        self.assertEqual(
            [column.key for column in matrix.columns],
            [("followup_arm_1", ""), ("baseline_arm_1", "")],
        )
        self.assertEqual(
            [row.form_name for row in matrix.rows],
            ["takip", "multiparametrik_mr"],
        )
        self.assertEqual(matrix.columns[0].repeat_actions, [actions[0]])
        repeat_cell = matrix.cell("multiparametrik_mr", ("baseline_arm_1", ""))
        self.assertEqual(repeat_cell.targets, [])
        self.assertEqual(repeat_cell.repeat_actions, [actions[1]])
        self.assertEqual(matrix.repeat_cards, [])

    def test_explicit_redcap_order_positions_action_only_events_and_forms(self) -> None:
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="baseline_form",
                    title="Baseline Form",
                    event_id="baseline_arm_1",
                    event_label="Başlangıç",
                    fields=[FormFieldModel("base", "baseline_form", "Base", "text", "A")],
                ),
                FormSectionModel(
                    form_name="result_form",
                    title="Result Form",
                    event_id="result_arm_1",
                    event_label="Sonuç",
                    fields=[FormFieldModel("result", "result_form", "Result", "text", "B")],
                ),
            ],
        )
        action = {
            "kind": "event",
            "event_id": "quality_arm_1",
            "event_label": "Hayat Kalitesi",
            "form_labels": {"quality_form": "Hayat Kalitesi"},
            "label": "Event: Hayat Kalitesi #1",
        }

        matrix = build_record_matrix(
            model,
            [action],
            event_order=["baseline_arm_1", "quality_arm_1", "result_arm_1"],
            form_order=["baseline_form", "quality_form", "result_form"],
        )

        self.assertEqual(
            [column.event_id for column in matrix.columns],
            ["baseline_arm_1", "quality_arm_1", "result_arm_1"],
        )
        self.assertEqual(
            [row.form_name for row in matrix.rows],
            ["baseline_form", "quality_form", "result_form"],
        )

    def test_derives_empty_partial_and_filled_states(self) -> None:
        matrix = build_record_matrix(record_model(), repeat_actions())

        patient = matrix.cell("hasta_bilgileri", ("tibbi_bilgiler_arm_1", "")).targets[0]
        repeats = matrix.cell("tan_laboratuvar_sonucu", ("tibbi_bilgiler_arm_1", "")).targets
        biopsy_two = matrix.cell("klasik_biyopsi", ("klasik_biyopsi_arm_1", "2")).targets[0]

        self.assertEqual(patient.status, MATRIX_STATUS_PARTIAL)
        self.assertEqual(repeats[0].status, MATRIX_STATUS_FILLED)
        self.assertEqual(repeats[1].status, MATRIX_STATUS_PARTIAL)
        self.assertEqual(biopsy_two.status, MATRIX_STATUS_EMPTY)

    def test_required_fields_define_matrix_status_not_redcap_completion_code(self) -> None:
        sections = [
            FormSectionModel(
                form_name="required_complete",
                title="Required complete",
                event_id="baseline_arm_1",
                completion_status="0",
                completion_present=True,
                fields=[
                    FormFieldModel("required", "required_complete", "Required", "text", "A", required=True),
                    FormFieldModel("optional", "required_complete", "Optional", "text", ""),
                ],
            ),
            FormSectionModel(
                form_name="required_missing",
                title="Required missing",
                event_id="baseline_arm_1",
                completion_status="2",
                completion_present=True,
                fields=[
                    FormFieldModel("required", "required_missing", "Required", "text", "", required=True),
                    FormFieldModel("optional", "required_missing", "Optional", "text", "A"),
                ],
            ),
            FormSectionModel(
                form_name="optional_filled",
                title="Optional filled",
                event_id="baseline_arm_1",
                completion_status="1",
                completion_present=True,
                fields=[FormFieldModel("optional", "optional_filled", "Optional", "text", "A")],
            ),
            FormSectionModel(
                form_name="optional_empty",
                title="Optional empty",
                event_id="baseline_arm_1",
                completion_status="2",
                completion_present=True,
                fields=[FormFieldModel("optional", "optional_empty", "Optional", "text", "")],
            ),
        ]
        matrix = build_record_matrix(
            FormRenderModel(project_id="17", record="1", title="Record 1", sections=sections)
        )

        statuses = [
            matrix.cell(section.form_name, ("baseline_arm_1", "")).targets[0].status
            for section in sections
        ]

        self.assertEqual(
            statuses,
            [MATRIX_STATUS_FILLED, MATRIX_STATUS_PARTIAL, MATRIX_STATUS_FILLED, MATRIX_STATUS_EMPTY],
        )


class DataEntryRecordMatrixWidgetTests(unittest.TestCase):
    def test_emits_exact_section_and_repeat_action_from_contextual_controls(self) -> None:
        get_qapplication()
        widget = DataEntryRecordMatrix(language="tr")
        selected = []
        repeated = []
        widget.targetActivated.connect(selected.append)
        widget.repeatActionRequested.connect(repeated.append)
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())

        self.assertEqual(len(widget.target_buttons), 5)
        self.assertEqual(
            {button.text() for _, button in widget.repeat_buttons},
            {"+", "+ Yeni Klasik Biyopsi ekle"},
        )

        english_widget = DataEntryRecordMatrix(language="en")
        english_widget.set_record_model(record_model(), repeat_actions=repeat_actions())
        english_event_add = next(
            button
            for action, button in english_widget.repeat_buttons
            if action["kind"] == "event"
        )
        self.assertEqual(english_event_add.text(), "+ Add new Klasik Biyopsi")

        widget.target_buttons[2].click()
        form_add = next(button for action, button in widget.repeat_buttons if action["kind"] == "form")
        event_add = next(button for action, button in widget.repeat_buttons if action["kind"] == "event")
        self.assertEqual(form_add.parent().objectName(), "DataEntryRecordMatrixCell")
        self.assertEqual(form_add.parent().property("form_name"), "tan_laboratuvar_sonucu")
        self.assertTrue(form_add.property("compact"))
        form_add.click()
        event_add.click()

        self.assertEqual(selected, [2])
        self.assertTrue(widget.target_buttons[2].property("active"))
        self.assertEqual([action["kind"] for action in repeated], ["form", "event"])

    def test_repeating_instrument_targets_are_numbered_inside_one_cell(self) -> None:
        get_qapplication()
        widget = DataEntryRecordMatrix(language="tr")
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())

        self.assertEqual(widget.target_buttons[1].text(), "●  #1")
        self.assertEqual(widget.target_buttons[2].text(), "●  #2")
        self.assertIn("Tanı Laboratuvar Sonucu #2", widget.target_buttons[2].toolTip())
        self.assertEqual(widget.target_buttons[0].text(), "●")

    def test_empty_repeating_instrument_still_renders_inline_add_control(self) -> None:
        get_qapplication()
        action = {
            "kind": "form",
            "form_name": "repeat_form",
            "form_label": "Repeat Form",
            "event_id": "baseline_arm_1",
            "event_label": "Baseline",
            "label": "Form: Baseline / Repeat Form #1",
        }
        widget = DataEntryRecordMatrix(language="tr")
        widget.set_record_model(
            FormRenderModel(project_id="17", record="1", title="Record 1", sections=[]),
            repeat_actions=[action],
        )

        self.assertEqual(len(widget.repeat_buttons), 1)
        _, add_button = widget.repeat_buttons[0]
        self.assertEqual(add_button.text(), "+")
        self.assertEqual(add_button.parent().objectName(), "DataEntryRecordMatrixCell")
        self.assertEqual(add_button.parent().property("event_id"), "baseline_arm_1")


if __name__ == "__main__":
    unittest.main()
