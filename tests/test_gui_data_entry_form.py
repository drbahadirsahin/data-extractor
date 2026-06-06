import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data_entry_form_model import (
    DATE_EDITOR,
    FormChoiceModel,
    FormFieldModel,
    FormRenderModel,
    FormSectionModel,
)
from gui.data_entry_form import DataEntryFormWidget, DataEntryNavButton


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class GuiDataEntryFormTests(unittest.TestCase):
    def test_renders_editors_and_collects_flat_values(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="demographics",
                        title="Demographics",
                        fields=[
                            FormFieldModel(
                                field_name="hasta_ad",
                                form_name="demographics",
                                label="Name",
                                editor="text",
                                value="AB",
                            ),
                            FormFieldModel(
                                field_name="stage",
                                form_name="demographics",
                                label="Stage",
                                editor="dropdown",
                                value="2",
                                choices=[
                                    FormChoiceModel("1", "T1"),
                                    FormChoiceModel("2", "T2"),
                                ],
                            ),
                            FormFieldModel(
                                field_name="risk",
                                form_name="demographics",
                                label="Risk",
                                editor="checkbox",
                                value=["1"],
                                choices=[
                                    FormChoiceModel("1", "Smoking"),
                                    FormChoiceModel("2", "Diabetes"),
                                ],
                            ),
                            FormFieldModel(
                                field_name="info",
                                form_name="demographics",
                                label="Info",
                                editor="description",
                                value="Readonly help",
                                read_only=True,
                            ),
                        ],
                    )
                ],
            )
        )

        values = form.collect_values()

        self.assertEqual(values["hasta_ad"], "AB")
        self.assertEqual(values["stage"], "2")
        self.assertEqual(values["risk___1"], "1")
        self.assertEqual(values["risk___2"], "0")
        self.assertNotIn("info", values)

        form.editor_widgets["hasta_ad"].setText("EF")
        form.editor_widgets["risk"][1].setChecked(True)
        change_set = form.collect_change_set()
        self.assertEqual([(item.field_name, item.new_value) for item in change_set.changes], [
            ("hasta_ad", "EF"),
            ("risk___2", "1"),
        ])

    def test_field_rows_expose_filled_empty_and_required_missing_states(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel("filled", "form", "Filled", "text", value="A"),
                            FormFieldModel("required", "form", "Required", "text", value="", required=True),
                            FormFieldModel("optional", "form", "Optional", "text", value=""),
                        ],
                    )
                ],
            )
        )

        self.assertEqual(form.field_rows["filled"].property("field_state"), "filled")
        self.assertEqual(form.field_rows["required"].property("field_state"), "required_missing")
        self.assertEqual(form.field_rows["optional"].property("field_state"), "empty")

        form.editor_widgets["required"].setText("B")

        self.assertEqual(form.field_rows["required"].property("field_state"), "filled")

    def test_radio_selection_can_be_cleared(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel(
                                "yasiyor_mu",
                                "form",
                                "Yaşıyor mu",
                                "radio",
                                value="1",
                                choices=[FormChoiceModel("1", "Evet"), FormChoiceModel("0", "Hayır")],
                            ),
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QToolButton

        clear_button = form.widget.findChild(QToolButton, "DataEntryClearRadioButton")

        self.assertIsNotNone(clear_button)
        self.assertTrue(clear_button.isEnabled())
        self.assertEqual(form.collect_values()["yasiyor_mu"], "1")

        clear_button.click()

        self.assertIsNone(form.editor_widgets["yasiyor_mu"].checkedButton())
        self.assertFalse(clear_button.isEnabled())
        self.assertEqual(form.collect_values()["yasiyor_mu"], "")
        self.assertEqual(form.field_rows["yasiyor_mu"].property("field_state"), "empty")
        change_set = form.collect_change_set()
        self.assertEqual([(item.field_name, item.old_value, item.new_value) for item in change_set.changes], [
            ("yasiyor_mu", "1", ""),
        ])

    def test_number_text_editor_normalizes_decimal_comma_before_collection(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
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
                                "",
                                validation="number",
                            )
                        ],
                    )
                ],
            )
        )

        editor = form.editor_widgets["psa"]
        editor.setText("14,46")

        self.assertEqual(form.collect_values()["psa"], "14.46")

        editor.editingFinished.emit()

        self.assertEqual(editor.text(), "14.46")
        self.assertEqual(form.collect_values()["psa"], "14.46")

    def test_number_text_editor_keeps_dot_decimal_input_under_turkish_locale(self) -> None:
        get_qapplication()
        from PySide6.QtCore import QLocale
        from PySide6.QtTest import QTest

        previous_locale = QLocale()
        QLocale.setDefault(QLocale("tr_TR"))
        try:
            form = DataEntryFormWidget(
                FormRenderModel(
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
                                    "",
                                    validation="number",
                                )
                            ],
                        )
                    ],
                )
            )
            editor = form.editor_widgets["psa"]

            QTest.keyClicks(editor, "14.25")
            editor.editingFinished.emit()

            self.assertEqual(editor.text(), "14.25")
            self.assertEqual(form.collect_values()["psa"], "14.25")
        finally:
            QLocale.setDefault(previous_locale)

    def test_number_text_editor_normalizes_scientific_notation_before_collection(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
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
        )

        editor = form.editor_widgets["hasta_boy"]

        self.assertEqual(form.collect_values()["hasta_boy"], "1425")

        editor.editingFinished.emit()

        self.assertEqual(editor.text(), "1425")
        self.assertEqual(form.collect_values()["hasta_boy"], "1425")

    def test_set_model_replaces_existing_editors(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="One",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel(
                                field_name="first",
                                form_name="form",
                                label="First",
                                editor="text",
                                value="A",
                            )
                        ],
                    )
                ],
            )
        )

        form.set_model(
            FormRenderModel(
                project_id="17",
                record="2",
                title="Two",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel(
                                field_name="second",
                                form_name="form",
                                label="Second",
                                editor="textarea",
                                value="B",
                            )
                        ],
                    )
                ],
            )
        )

        values = form.collect_values()
        self.assertNotIn("first", values)
        self.assertEqual(values["second"], "B")

    def test_multiple_forms_are_rendered_with_readable_side_nav_and_opens_first_filled_form(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="a",
                        title="Form A",
                        fields=[FormFieldModel("a1", "a", "A1", "text")],
                    ),
                    FormSectionModel(
                        form_name="b",
                        title="Form B",
                        fields=[FormFieldModel("b1", "b", "B1", "text", value="filled")],
                    ),
                ],
            )
        )
        from PySide6.QtWidgets import QScrollArea, QStackedWidget

        form_nav = form.widget.findChild(QScrollArea, "DataEntryFormNavScroll")
        nav_buttons = form.widget.findChildren(DataEntryNavButton, "DataEntryFormNavButton")
        form_stack = form.widget.findChild(QStackedWidget, "DataEntryFormStack")

        self.assertIsNotNone(form_nav)
        self.assertIsNotNone(form_stack)
        self.assertEqual(len(nav_buttons), 2)
        self.assertEqual(form_stack.count(), 2)
        self.assertEqual(nav_buttons[0].text(), "Form A")
        self.assertEqual(nav_buttons[1].text(), "Form B\n1/1 alan dolu")
        self.assertTrue(nav_buttons[1].isChecked())
        self.assertEqual(form.current_section().form_name, "b")
        self.assertNotIn("a1", form.editor_widgets)
        self.assertIn("b1", form.editor_widgets)

        nav_buttons[0].click()

        self.assertIn("a1", form.editor_widgets)
        self.assertEqual(form.current_section().form_name, "a")

    def test_event_sections_are_grouped_under_event_headers(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="a",
                        title="Hasta Bilgileri",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        fields=[FormFieldModel("a1", "a", "A1", "text")],
                    ),
                    FormSectionModel(
                        form_name="b",
                        title="Laboratuvar",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        fields=[FormFieldModel("b1", "b", "B1", "text")],
                    ),
                    FormSectionModel(
                        form_name="a",
                        title="Hasta Bilgileri",
                        event_id="followup_arm_1",
                        event_label="İzlem",
                        fields=[FormFieldModel("a1", "a", "A1", "text", value="filled")],
                    ),
                ],
            )
        )
        from PySide6.QtWidgets import QLabel

        event_labels = form.widget.findChildren(QLabel, "DataEntryFormNavEvent")
        nav_buttons = form.widget.findChildren(DataEntryNavButton, "DataEntryFormNavButton")

        self.assertEqual([item.text() for item in event_labels], ["Başlangıç", "İzlem"])
        self.assertEqual(nav_buttons[0].text(), "Hasta Bilgileri")
        self.assertEqual(nav_buttons[1].text(), "Laboratuvar")
        self.assertEqual(nav_buttons[2].text(), "Hasta Bilgileri\n1/1 alan dolu")
        self.assertEqual(form.current_section().event_id, "followup_arm_1")

    def test_repeating_form_instances_stay_under_the_event_without_repeating_word(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="tan_laboratuvar_sonucu",
                        title="Tanı Laboratuvar Sonucu",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        repeat_instrument="tan_laboratuvar_sonucu",
                        instance="1",
                        fields=[FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "4.2")],
                    ),
                    FormSectionModel(
                        form_name="tan_laboratuvar_sonucu",
                        title="Tanı Laboratuvar Sonucu",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        repeat_instrument="tan_laboratuvar_sonucu",
                        instance="2",
                        fields=[FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "5.1")],
                    ),
                ],
            )
        )
        from PySide6.QtWidgets import QLabel

        event_labels = form.widget.findChildren(QLabel, "DataEntryFormNavEvent")
        nav_buttons = form.widget.findChildren(DataEntryNavButton, "DataEntryFormNavButton")

        self.assertEqual([item.text() for item in event_labels], ["Başlangıç"])
        self.assertEqual(nav_buttons[0].text(), "Tanı Laboratuvar Sonucu #1\n1/1 alan dolu")
        self.assertEqual(nav_buttons[1].text(), "Tanı Laboratuvar Sonucu #2\n1/1 alan dolu")
        self.assertNotIn("Tekrar", nav_buttons[0].text())

    def test_repeat_actions_are_contextual_in_the_form_navigation(self) -> None:
        get_qapplication()
        triggered = []
        form = DataEntryFormWidget(language="tr")
        form.set_model(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="tan_laboratuvar_sonucu",
                        title="Tanı Laboratuvar Sonucu",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        repeat_instrument="tan_laboratuvar_sonucu",
                        instance="1",
                        fields=[FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "4.2")],
                    ),
                    FormSectionModel(
                        form_name="tan_laboratuvar_sonucu",
                        title="Tanı Laboratuvar Sonucu",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        repeat_instrument="tan_laboratuvar_sonucu",
                        instance="2",
                        fields=[FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "5.1")],
                    ),
                    FormSectionModel(
                        form_name="tan_laboratuvar_sonucu",
                        title="Tanı Laboratuvar Sonucu",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        repeat_instrument="tan_laboratuvar_sonucu",
                        instance="3",
                        fields=[FormFieldModel("psa", "tan_laboratuvar_sonucu", "PSA", "text", "6.3")],
                    ),
                    FormSectionModel(
                        form_name="hasta_bilgileri",
                        title="Hasta Bilgileri",
                        event_id="followup_arm_1",
                        event_label="İzlem",
                        fields=[FormFieldModel("hasta_ad", "hasta_bilgileri", "Hasta adı", "text", "AH")],
                    ),
                ],
            ),
            repeat_actions=[
                {
                    "kind": "event",
                    "event_id": "followup_arm_1",
                    "label": "Event: İzlem #2",
                },
                {
                    "kind": "form",
                    "form_name": "tan_laboratuvar_sonucu",
                    "event_id": "baseline_arm_1",
                    "label": "Form: Başlangıç / Tanı Laboratuvar Sonucu #4",
                },
            ],
            repeat_action_handler=lambda option: triggered.append(option),
        )
        from PySide6.QtWidgets import QPushButton, QToolButton

        panel_buttons = form.widget.findChildren(QPushButton, "DataEntryRepeatPanelButton")
        inline_buttons = form.widget.findChildren(QToolButton, "DataEntryFormNavInlineAdd")
        event_buttons = form.widget.findChildren(QToolButton, "DataEntryFormNavEventAdd")

        self.assertEqual(panel_buttons, [])
        self.assertEqual(len(inline_buttons), 1)
        self.assertEqual(inline_buttons[0].text(), "+")
        self.assertEqual(inline_buttons[0].width(), 28)
        self.assertIn("#4", inline_buttons[0].toolTip())
        self.assertEqual(len(event_buttons), 1)
        self.assertEqual(event_buttons[0].text(), "+")
        self.assertEqual(event_buttons[0].width(), 28)
        self.assertIn("İzlem", event_buttons[0].toolTip())
        inline_buttons[0].click()
        event_buttons[0].click()
        self.assertEqual([item["kind"] for item in triggered], ["form", "event"])

    def test_calculated_fields_update_from_visible_form_values(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="hasta_bilgileri",
                        title="Hasta Bilgileri",
                        fields=[
                            FormFieldModel("hasta_kilo", "hasta_bilgileri", "Kilo", "text", "82"),
                            FormFieldModel("hasta_boy", "hasta_bilgileri", "Boy", "text", "180"),
                            FormFieldModel(
                                "hasta_vki",
                                "hasta_bilgileri",
                                "VKİ",
                                "readonly",
                                field_type="calc",
                                read_only=True,
                                calc_expression="round(([hasta_kilo]*10000)/([hasta_boy]*[hasta_boy]),2)",
                            ),
                        ],
                    )
                ],
            )
        )

        self.assertEqual(form.editor_widgets["hasta_vki"].text(), "25.31")

        form.editor_widgets["hasta_kilo"].setText("90")

        self.assertEqual(form.editor_widgets["hasta_vki"].text(), "27.78")

    def test_simple_branching_logic_hides_and_shows_fields(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel("has_detail", "form", "Has detail", "text", value=""),
                            FormFieldModel(
                                "detail",
                                "form",
                                "Detail",
                                "text",
                                value="",
                                branching_logic="[has_detail] = '1'",
                            ),
                        ],
                    )
                ],
            )
        )

        self.assertTrue(form.field_rows["detail"].isHidden())

        form.editor_widgets["has_detail"].setText("1")

        self.assertFalse(form.field_rows["detail"].isHidden())

    def test_date_editor_collects_ymd_values(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel(
                                field_name="dogum_tarihi",
                                form_name="form",
                                label="Doğum Tarihi",
                                editor=DATE_EDITOR,
                                value="2026-05-28",
                            )
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QToolButton

        self.assertEqual(form.collect_values()["dogum_tarihi"], "2026-05-28")
        self.assertEqual(form.widget.findChildren(QToolButton, "DataEntryDateButton"), [])

    def test_date_editor_keeps_blank_blank_and_normalizes_common_date_formats(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel("blank_date", "form", "Boş tarih", DATE_EDITOR, value=""),
                            FormFieldModel("dot_date", "form", "Noktalı tarih", DATE_EDITOR, value="16.01.2019"),
                            FormFieldModel(
                                "datetime_date",
                                "form",
                                "Saatli tarih",
                                DATE_EDITOR,
                                value="2026-05-28 10:20:00",
                            ),
                        ],
                    )
                ],
            )
        )

        values = form.collect_values()

        self.assertEqual(values["blank_date"], "")
        self.assertEqual(values["dot_date"], "2019-01-16")
        self.assertEqual(values["datetime_date"], "2026-05-28")

    def test_dynamic_sql_combo_keeps_existing_value_visible(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[
                            FormFieldModel(
                                field_name="mr_secimi",
                                form_name="form",
                                label="MR seçimi",
                                editor="dynamic_dropdown",
                                value="1. MR Tarihi: 2026-05-28",
                            )
                        ],
                    )
                ],
            )
        )

        self.assertEqual(form.collect_values()["mr_secimi"], "1. MR Tarihi: 2026-05-28")

    def test_blank_repeat_section_does_not_offer_add_repeat_action(self) -> None:
        get_qapplication()
        blank_section = FormSectionModel(
            form_name="multiparametrik_mr",
            title="Multiparametrik MR",
            repeat_instrument="multiparametrik_mr",
            instance="1",
            fields=[
                FormFieldModel(
                    field_name="mr_tarih_secimi",
                    form_name="multiparametrik_mr",
                    label="MR Tarihi",
                    editor="text",
                    value="",
                )
            ],
        )
        filled_section = FormSectionModel(
            form_name="multiparametrik_mr",
            title="Multiparametrik MR",
            repeat_instrument="multiparametrik_mr",
            instance="1",
            fields=[
                FormFieldModel(
                    field_name="mr_tarih_secimi",
                    form_name="multiparametrik_mr",
                    label="MR Tarihi",
                    editor="text",
                    value="2026-06-06",
                )
            ],
        )
        action = {
            "kind": "form",
            "form_name": "multiparametrik_mr",
            "event_id": "",
            "label": "Form ekle",
        }
        form = DataEntryFormWidget()
        form.set_model(
            FormRenderModel(project_id="17", record="1", title="Record 1", sections=[blank_section]),
            repeat_actions=[action],
        )

        self.assertIsNone(form.repeat_action_for_section(blank_section))

        form.set_model(
            FormRenderModel(project_id="17", record="1", title="Record 1", sections=[filled_section]),
            repeat_actions=[action],
        )

        self.assertIs(form.repeat_action_for_section(filled_section), action)

    def test_duplicate_event_fields_use_context_keys(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
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
                                "Hasta adı",
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
                                "Hasta adı",
                                "text",
                                "CD",
                                event_id="followup_arm_1",
                                context_key="hasta_ad@@event=followup_arm_1@@repeat=@@instance=",
                            )
                        ],
                    ),
                ],
            )
        )

        nav_buttons = form.widget.findChildren(DataEntryNavButton, "DataEntryFormNavButton")
        nav_buttons[1].click()
        values = form.collect_values()

        self.assertEqual(values["hasta_ad@@event=baseline_arm_1@@repeat=@@instance="], "AB")
        self.assertEqual(values["hasta_ad@@event=followup_arm_1@@repeat=@@instance="], "CD")


if __name__ == "__main__":
    unittest.main()
