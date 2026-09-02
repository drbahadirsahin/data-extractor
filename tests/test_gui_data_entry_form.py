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
    def test_checkbox_style_has_visible_glyph_and_all_interaction_states(self) -> None:
        from pathlib import Path

        from gui.clinical_styles import CLINICAL_STYLE

        check_icon = Path(__file__).parents[1] / "gui" / "assets" / "checkbox_check.svg"

        self.assertTrue(check_icon.is_file())
        self.assertIn(check_icon.as_posix(), CLINICAL_STYLE)
        self.assertNotIn("__CHECKBOX_CHECK_ICON__", CLINICAL_STYLE)
        self.assertIn("QCheckBox::indicator:unchecked:hover", CLINICAL_STYLE)
        self.assertIn("QCheckBox::indicator:checked:hover", CLINICAL_STYLE)
        self.assertIn("QCheckBox::indicator:unchecked:disabled", CLINICAL_STYLE)
        self.assertIn("QCheckBox::indicator:checked:disabled", CLINICAL_STYLE)

    def test_radio_style_uses_circular_svg_assets_for_all_interaction_states(self) -> None:
        from pathlib import Path

        from gui.clinical_styles import CLINICAL_STYLE

        asset_dir = Path(__file__).parents[1] / "gui" / "assets"
        filenames = {
            "radio_unchecked.svg",
            "radio_unchecked_hover.svg",
            "radio_checked.svg",
            "radio_checked_hover.svg",
            "radio_disabled.svg",
            "radio_checked_disabled.svg",
        }

        for filename in filenames:
            self.assertTrue((asset_dir / filename).is_file())
            self.assertIn((asset_dir / filename).as_posix(), CLINICAL_STYLE)
        self.assertNotIn("__RADIO_", CLINICAL_STYLE)
        self.assertIn("QRadioButton::indicator:checked", CLINICAL_STYLE)
        self.assertIn("QRadioButton::indicator:checked:hover", CLINICAL_STYLE)
        self.assertIn("QRadioButton::indicator:unchecked:disabled", CLINICAL_STYLE)
        self.assertNotIn("QRadioButton::indicator:checked {\n    background", CLINICAL_STYLE)

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

    def test_event_sections_use_collapsible_navigation_and_open_first_filled_form(self) -> None:
        app = get_qapplication()
        from PySide6.QtWidgets import QFrame

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
                        event_label="İzlem #1",
                        instance="1",
                        fields=[FormFieldModel("a1", "a", "A1", "text", value="filled")],
                    ),
                    FormSectionModel(
                        form_name="a",
                        title="Hasta Bilgileri",
                        event_id="followup_arm_1",
                        event_label="İzlem #2",
                        instance="2",
                        fields=[FormFieldModel("a1", "a", "A1", "text")],
                    ),
                ],
            )
        )
        form.widget.show()
        app.processEvents()

        self.assertIsNotNone(form.event_nav)
        self.assertEqual(form.widget.findChildren(QFrame, "DataEntryFormEmpty"), [])
        self.assertEqual(
            [group.key for group in form.event_nav.nav_model.groups],
            ["baseline_arm_1", "followup_arm_1"],
        )
        self.assertEqual(
            [item.form_name for item in form.event_nav.nav_model.groups[0].instances[0].forms],
            ["a", "b"],
        )
        self.assertEqual(form.current_section_index(), 2)
        self.assertEqual(form.current_section().event_id, "followup_arm_1")
        self.assertTrue(form.event_nav.target_buttons[2].property("active"))
        self.assertEqual(
            set(form.event_nav.instance_buttons),
            {("followup_arm_1", "1"), ("followup_arm_1", "2")},
        )
        self.assertFalse(form.event_nav.instance_bodies[("followup_arm_1", "1")].isHidden())
        self.assertTrue(form.event_nav.instance_bodies[("followup_arm_1", "2")].isHidden())
        self.assertTrue(form.event_nav.group_contents["baseline_arm_1"].isHidden())
        self.assertFalse(form.event_nav.group_contents["followup_arm_1"].isHidden())

        form.event_nav.instance_buttons[("followup_arm_1", "2")].click()

        self.assertTrue(form.event_nav.instance_bodies[("followup_arm_1", "1")].isHidden())
        self.assertFalse(form.event_nav.instance_bodies[("followup_arm_1", "2")].isHidden())
        self.assertEqual(form.event_nav.selected_instances()["followup_arm_1"], "2")

        form.event_nav.group_headers["baseline_arm_1"].click()

        self.assertFalse(form.event_nav.group_contents["baseline_arm_1"].isHidden())
        self.assertTrue(form.event_nav.group_headers["baseline_arm_1"].text().startswith("▾"))

    def test_repeating_form_instances_are_inline_chips_in_their_event_group(self) -> None:
        get_qapplication()
        action = {
            "kind": "form",
            "form_name": "tan_laboratuvar_sonucu",
            "event_id": "baseline_arm_1",
            "label": "Form: Başlangıç / Tanı Laboratuvar Sonucu #3",
        }
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
                ],
            ),
            repeat_actions=[action],
        )

        self.assertIsNotNone(form.event_nav)
        group = form.event_nav.nav_model.group("baseline_arm_1")
        self.assertIsNotNone(group)
        repeating_form = group.instances[0].forms[0]
        self.assertEqual(
            [target.instance for target in repeating_form.targets],
            ["1", "2"],
        )
        self.assertEqual(form.event_nav.target_buttons[0].text(), "#1")
        self.assertEqual(form.event_nav.target_buttons[1].text(), "#2")
        self.assertEqual(form.event_nav.instance_buttons, {})
        self.assertEqual(len(form.event_nav.repeat_buttons), 1)
        repeat_action, add_button = form.event_nav.repeat_buttons[0]
        self.assertEqual(repeat_action, action)
        self.assertEqual(add_button.text(), "+")
        self.assertEqual(add_button.parent().property("form_name"), "tan_laboratuvar_sonucu")

    def test_matching_event_and_form_headings_are_not_repeated_and_status_updates_live(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="klasik_biyopsi",
                        title="Klasik Biyopsi",
                        event_id="biyopsi_arm_1",
                        event_label="Klasik Biyopsi #1",
                        instance="1",
                        fields=[
                            FormFieldModel(
                                "biyopsi_tarihi",
                                "klasik_biyopsi",
                                "Tarih",
                                "text",
                                "",
                                required=True,
                            )
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QLabel

        event_titles = form.widget.findChildren(QLabel, "SectionEventTitle")
        section_titles = form.widget.findChildren(QLabel, "SectionTitle")
        self.assertEqual(event_titles, [])
        self.assertIn("Klasik Biyopsi", [label.text() for label in section_titles])
        self.assertEqual(form.event_nav.status_labels[0].text(), "!")

        form.editor_widgets["biyopsi_tarihi"].setText("2026-07-11")

        self.assertEqual(form.event_nav.status_labels[0].text(), "✓")
        self.assertTrue(form.event_nav.status_labels[0].property("dirty"))

    def test_repeat_actions_are_contextual_in_the_event_navigation(self) -> None:
        get_qapplication()
        triggered = []
        event_action = {
            "kind": "event",
            "event_id": "followup_arm_1",
            "label": "Event: İzlem #2",
        }
        form_action = {
            "kind": "form",
            "form_name": "tan_laboratuvar_sonucu",
            "event_id": "baseline_arm_1",
            "label": "Form: Başlangıç / Tanı Laboratuvar Sonucu #4",
        }
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
            repeat_actions=[event_action, form_action],
            repeat_action_handler=lambda option: triggered.append(option),
        )

        self.assertIsNotNone(form.event_nav)
        buttons_by_kind = {
            option["kind"]: button
            for option, button in form.event_nav.repeat_buttons
        }
        self.assertEqual(set(buttons_by_kind), {"event", "form"})
        self.assertTrue(all(button.isEnabled() for button in buttons_by_kind.values()))
        form_button = buttons_by_kind["form"]
        event_button = buttons_by_kind["event"]
        self.assertEqual(form_button.text(), "+")
        self.assertEqual(event_button.text(), "+")
        self.assertEqual(form_button.parent().property("form_name"), "tan_laboratuvar_sonucu")
        self.assertEqual(event_button.parent().property("event_id"), "followup_arm_1")
        self.assertEqual(form_button.toolTip(), "Tanı Laboratuvar Sonucu için yeni tekrar ekle")
        self.assertEqual(event_button.toolTip(), "Yeni İzlem kaydı ekle")
        form_button.click()
        event_button.click()
        self.assertEqual(triggered, [form_action, event_action])

    def test_repeat_action_does_not_require_the_previous_instance_to_be_filled(self) -> None:
        get_qapplication()
        section = FormSectionModel(
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
        action = {
            "kind": "form",
            "form_name": "multiparametrik_mr",
            "event_id": "",
            "label": "Form: Multiparametrik MR #2",
        }
        triggered = []
        form = DataEntryFormWidget(language="tr")
        form.set_model(
            FormRenderModel(project_id="17", record="1", title="Record 1", sections=[section]),
            repeat_actions=[action],
            repeat_action_handler=lambda option: triggered.append(option),
        )
        self.assertIsNotNone(form.event_nav)
        self.assertEqual(len(form.event_nav.repeat_buttons), 1)
        repeat_action, add_button = form.event_nav.repeat_buttons[0]
        self.assertEqual(repeat_action, action)
        self.assertEqual(add_button.parent().property("form_name"), "multiparametrik_mr")
        self.assertTrue(add_button.isEnabled())

        add_button.click()
        self.assertEqual(triggered, [action])

    def test_repeat_event_and_form_actions_coexist_for_same_event(self) -> None:
        get_qapplication()
        model = FormRenderModel(
            project_id="17",
            record="1",
            title="Record 1",
            sections=[
                FormSectionModel(
                    form_name="multiparametrik_mr",
                    title="Multiparametrik MR",
                    event_id="followup_arm_1",
                    event_label="İzlem",
                    repeat_instrument="multiparametrik_mr",
                    instance="1",
                    fields=[FormFieldModel("mr_not", "multiparametrik_mr", "MR notu", "text", "A")],
                ),
                FormSectionModel(
                    form_name="multiparametrik_mr",
                    title="Multiparametrik MR",
                    event_id="followup_arm_1",
                    event_label="İzlem",
                    repeat_instrument="multiparametrik_mr",
                    instance="2",
                    fields=[FormFieldModel("mr_not", "multiparametrik_mr", "MR notu", "text", "B")],
                ),
            ],
        )
        actions = [
            {"kind": "event", "event_id": "followup_arm_1", "label": "Event: İzlem #3"},
            {
                "kind": "form",
                "form_name": "multiparametrik_mr",
                "event_id": "followup_arm_1",
                "label": "Form: İzlem / Multiparametrik MR #3",
            },
        ]
        triggered = []
        form = DataEntryFormWidget(language="tr")
        form.set_model(model, repeat_actions=actions, repeat_action_handler=lambda option: triggered.append(option))

        self.assertIsNotNone(form.event_nav)
        self.assertEqual(len(form.event_nav.repeat_buttons), 2)
        self.assertEqual(form.event_nav.instance_buttons, {})
        buttons_by_kind = {
            option["kind"]: button
            for option, button in form.event_nav.repeat_buttons
        }
        self.assertEqual(buttons_by_kind["event"].parent().property("event_id"), "followup_arm_1")
        self.assertEqual(buttons_by_kind["form"].parent().property("form_name"), "multiparametrik_mr")
        self.assertTrue(all(button.isEnabled() for button in buttons_by_kind.values()))
        buttons_by_kind["event"].click()
        buttons_by_kind["form"].click()
        self.assertEqual(triggered, actions)

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

    def test_calculated_fields_remain_readonly_display_values(self) -> None:
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
        from PySide6.QtWidgets import QLabel

        calculated = form.editor_widgets["hasta_vki"]

        self.assertIsInstance(calculated, QLabel)
        self.assertTrue(calculated.property("calculated"))
        self.assertEqual(calculated.text(), "25.31")
        self.assertNotIn("hasta_vki", form.collect_values())

        applied = form.apply_values({"hasta_kilo": "90", "hasta_vki": "99.99"})

        self.assertEqual(applied, 1)
        self.assertEqual(form.editor_widgets["hasta_kilo"].text(), "90")
        self.assertEqual(calculated.text(), "27.78")
        self.assertNotEqual(calculated.text(), "99.99")
        self.assertNotIn("hasta_vki", form.collect_values(include_hidden=True))

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

    def test_hidden_branching_field_keeps_its_value_until_visible_again(self) -> None:
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
                            FormFieldModel("has_detail", "form", "Has detail", "text", value="1"),
                            FormFieldModel(
                                "detail",
                                "form",
                                "Detail",
                                "text",
                                value="Korunacak değer",
                                branching_logic="[has_detail] = '1'",
                            ),
                        ],
                    )
                ],
            )
        )

        self.assertFalse(form.field_rows["detail"].isHidden())
        self.assertEqual(form.collect_values()["detail"], "Korunacak değer")

        form.editor_widgets["has_detail"].setText("0")

        self.assertTrue(form.field_rows["detail"].isHidden())
        self.assertNotIn("detail", form.collect_values())
        self.assertEqual(form.collect_values(include_hidden=True)["detail"], "Korunacak değer")

        form.editor_widgets["has_detail"].setText("1")

        self.assertFalse(form.field_rows["detail"].isHidden())
        self.assertEqual(form.editor_widgets["detail"].text(), "Korunacak değer")
        self.assertEqual(form.collect_values()["detail"], "Korunacak değer")

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
        from PySide6.QtCore import QDate, Qt
        from PySide6.QtWidgets import QCalendarWidget, QToolButton

        self.assertEqual(form.collect_values()["dogum_tarihi"], "2026-05-28")
        buttons = form.widget.findChildren(QToolButton, "DataEntryDateButton")
        self.assertEqual(len(buttons), 1)
        self.assertTrue(buttons[0].isEnabled())
        calendar = form.widget.findChild(QCalendarWidget, "DataEntryCalendar")
        self.assertIsNotNone(calendar)
        self.assertTrue(calendar.isNavigationBarVisible())
        self.assertEqual(calendar.firstDayOfWeek(), Qt.DayOfWeek.Monday)
        self.assertEqual(
            calendar.verticalHeaderFormat(),
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader,
        )

        calendar.clicked.emit(QDate(2027, 1, 9))

        self.assertEqual(form.collect_values()["dogum_tarihi"], "2027-01-09")

    def test_filled_editable_date_can_be_cleared_without_breaking_calendar_selection(self) -> None:
        app = get_qapplication()
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
                                "visit_date",
                                "form",
                                "Visit date",
                                DATE_EDITOR,
                                value="2026-08-12",
                            )
                        ],
                    )
                ],
            )
        )
        from PySide6.QtCore import QDate
        from PySide6.QtWidgets import QToolButton

        editor = form.editor_widgets["visit_date"]
        line_edit = editor._data_entry_date_line_edit
        calendar = editor._data_entry_date_calendar
        clear_button = editor.findChild(QToolButton, "DataEntryDateClearButton")
        form.widget.resize(520, 320)
        form.widget.show()
        app.processEvents()

        self.assertIsNotNone(clear_button)
        self.assertTrue(clear_button.isVisible())
        self.assertTrue(clear_button.isEnabled())

        clear_button.click()
        app.processEvents()

        self.assertEqual(line_edit.text(), "")
        self.assertEqual(form.collect_values()["visit_date"], "")
        self.assertTrue(clear_button.isHidden() or not clear_button.isEnabled())
        self.assertFalse(editor._data_entry_date_menu.isVisible())

        calendar.clicked.emit(QDate(2027, 1, 9))
        app.processEvents()

        self.assertEqual(line_edit.text(), "2027-01-09")
        self.assertEqual(form.collect_values()["visit_date"], "2027-01-09")
        self.assertTrue(clear_button.isVisible())
        self.assertTrue(clear_button.isEnabled())
        form.widget.close()

    def test_empty_editable_date_does_not_offer_an_active_clear_action(self) -> None:
        app = get_qapplication()
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
                                "visit_date",
                                "form",
                                "Visit date",
                                DATE_EDITOR,
                                value="",
                            )
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QToolButton

        editor = form.editor_widgets["visit_date"]
        clear_button = editor.findChild(QToolButton, "DataEntryDateClearButton")
        form.widget.resize(520, 320)
        form.widget.show()
        app.processEvents()

        self.assertIsNotNone(clear_button)
        self.assertTrue(clear_button.isHidden() or not clear_button.isEnabled())
        self.assertEqual(form.collect_values()["visit_date"], "")
        form.widget.close()

    def test_readonly_date_clear_action_is_hidden_disabled_and_has_no_effect(self) -> None:
        app = get_qapplication()
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
                                "created_at",
                                "form",
                                "Created At",
                                DATE_EDITOR,
                                value="2026-07-10",
                                read_only=True,
                            )
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QToolButton

        editor = form.editor_widgets["created_at"]
        line_edit = editor._data_entry_date_line_edit
        clear_button = editor.findChild(QToolButton, "DataEntryDateClearButton")
        form.widget.resize(520, 320)
        form.widget.show()
        app.processEvents()

        self.assertIsNotNone(clear_button)
        self.assertFalse(clear_button.isVisible())
        self.assertFalse(clear_button.isEnabled())

        clear_button.click()
        app.processEvents()

        self.assertEqual(line_edit.text(), "2026-07-10")
        self.assertNotIn("created_at", form.collect_values())
        form.widget.close()

    def test_date_editor_opens_calendar_from_input_click_and_focus_without_text_reopening_it(self) -> None:
        app = get_qapplication()
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
                            FormFieldModel("name", "form", "Name", "text", value=""),
                            FormFieldModel("visit_date", "form", "Visit date", DATE_EDITOR, value=""),
                        ],
                    )
                ],
            )
        )
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QFocusEvent
        from PySide6.QtTest import QTest

        editor = form.editor_widgets["visit_date"]
        line_edit = editor._data_entry_date_line_edit
        menu = editor._data_entry_date_menu
        requests: list[bool] = []
        line_edit.calendarRequested.connect(lambda: requests.append(True))
        form.widget.resize(520, 320)
        form.widget.show()
        app.processEvents()

        QTest.mouseClick(line_edit, Qt.MouseButton.LeftButton)
        app.processEvents()

        self.assertTrue(menu.isVisible())
        self.assertEqual(len(requests), 1)

        menu.close()
        app.processEvents()
        request_count = len(requests)
        line_edit.setText("2027-01-09")
        app.processEvents()

        self.assertFalse(menu.isVisible())
        self.assertEqual(len(requests), request_count)

        focus_event = QFocusEvent(QEvent.Type.FocusIn, Qt.FocusReason.OtherFocusReason)
        app.sendEvent(line_edit, focus_event)
        app.processEvents()

        self.assertTrue(menu.isVisible())
        self.assertEqual(len(requests), request_count + 1)
        menu.close()
        form.widget.close()

    def test_calendar_year_step_buttons_are_visible_and_change_year(self) -> None:
        app = get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="form",
                        title="Form",
                        fields=[FormFieldModel("visit_date", "form", "Visit date", DATE_EDITOR, value="2026-07-11")],
                    )
                ],
            )
        )
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QAbstractSpinBox, QSpinBox, QToolButton

        editor = form.editor_widgets["visit_date"]
        calendar = editor._data_entry_date_calendar
        form.widget.resize(420, 260)
        form.widget.show()
        app.processEvents()
        QTest.mouseClick(editor._data_entry_date_line_edit, Qt.MouseButton.LeftButton)
        app.processEvents()
        year_button = calendar.findChild(QToolButton, "qt_calendar_yearbutton")
        self.assertIsNotNone(year_button)
        year_button.click()
        app.processEvents()

        year_spin = calendar.findChild(QSpinBox, "qt_calendar_yearedit")
        up_button = calendar.findChild(QToolButton, "DataEntryCalendarYearUp")
        down_button = calendar.findChild(QToolButton, "DataEntryCalendarYearDown")
        self.assertIsNotNone(year_spin)
        self.assertIsNotNone(up_button)
        self.assertIsNotNone(down_button)
        self.assertEqual(year_spin.buttonSymbols(), QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.assertTrue(up_button.isVisible())
        self.assertTrue(down_button.isVisible())

        original_year = year_spin.value()
        up_button.click()
        self.assertEqual(year_spin.value(), original_year + 1)
        down_button.click()
        self.assertEqual(year_spin.value(), original_year)
        calendar.close()

    def test_lazy_event_date_editor_opens_and_keeps_calendar_controls_and_value_in_sync(self) -> None:
        app = get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="hasta_bilgileri",
                        title="Hasta Bilgileri",
                        event_id="baseline_arm_1",
                        event_label="Başlangıç",
                        fields=[
                            FormFieldModel(
                                "hasta_ad",
                                "hasta_bilgileri",
                                "Hasta adı",
                                "text",
                                value="Ayşe",
                            )
                        ],
                    ),
                    FormSectionModel(
                        form_name="izlem",
                        title="İzlem",
                        event_id="followup_arm_1",
                        event_label="İzlem",
                        fields=[
                            FormFieldModel(
                                "izlem_tarihi",
                                "izlem",
                                "İzlem tarihi",
                                DATE_EDITOR,
                                value="",
                            )
                        ],
                    ),
                ],
            )
        )
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QSpinBox, QToolButton

        self.assertIsNotNone(form.event_nav)
        self.assertNotIn("izlem_tarihi", form.editor_widgets)
        form.widget.resize(680, 420)
        form.widget.show()
        app.processEvents()

        form.event_nav.target_buttons[1].click()
        app.processEvents()

        self.assertIn("izlem_tarihi", form.editor_widgets)
        editor = form.editor_widgets["izlem_tarihi"]
        applied = form.apply_values({"izlem_tarihi": "2029-03-14"})

        self.assertEqual(applied, 1)
        self.assertEqual(editor._data_entry_date_line_edit.text(), "2029-03-14")
        self.assertEqual(
            editor._data_entry_date_calendar.selectedDate().toString("yyyy-MM-dd"),
            "2029-03-14",
        )

        QTest.mouseClick(editor._data_entry_date_line_edit, Qt.MouseButton.LeftButton)
        app.processEvents()

        self.assertTrue(editor._data_entry_date_menu.isVisible())
        year_button = editor._data_entry_date_calendar.findChild(QToolButton, "qt_calendar_yearbutton")
        self.assertIsNotNone(year_button)
        year_button.click()
        app.processEvents()

        year_spin = editor._data_entry_date_calendar.findChild(QSpinBox, "qt_calendar_yearedit")
        up_button = editor._data_entry_date_calendar.findChild(QToolButton, "DataEntryCalendarYearUp")
        down_button = editor._data_entry_date_calendar.findChild(QToolButton, "DataEntryCalendarYearDown")
        self.assertIsNotNone(year_spin)
        self.assertIsNotNone(up_button)
        self.assertIsNotNone(down_button)
        self.assertEqual(year_spin.value(), 2029)
        self.assertTrue(up_button.isVisible())
        self.assertTrue(down_button.isVisible())

        editor._data_entry_date_menu.close()
        form.widget.close()

    def test_date_editor_normalizes_typed_date_and_keeps_invalid_text_visible(self) -> None:
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
                                value="",
                            )
                        ],
                    )
                ],
            )
        )
        editor = form.editor_widgets["dogum_tarihi"]
        line_edit = editor._data_entry_date_line_edit

        line_edit.setText("9.1.2027")
        line_edit.editingFinished.emit()

        self.assertEqual(line_edit.text(), "2027-01-09")
        self.assertEqual(editor._data_entry_date_calendar.selectedDate().toString("yyyy-MM-dd"), "2027-01-09")

        line_edit.setText("gecersiz")
        line_edit.editingFinished.emit()

        self.assertEqual(line_edit.text(), "gecersiz")

    def test_readonly_date_editor_disables_calendar_trigger(self) -> None:
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
                                field_name="created_at",
                                form_name="form",
                                label="Created At",
                                editor=DATE_EDITOR,
                                value="2026-07-10",
                                read_only=True,
                            )
                        ],
                    )
                ],
            )
        )

        editor = form.editor_widgets["created_at"]

        self.assertTrue(editor._data_entry_date_line_edit.isReadOnly())
        self.assertFalse(editor._data_entry_date_button.isEnabled())

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

    def test_section_headers_render_as_group_blocks(self) -> None:
        get_qapplication()
        form = DataEntryFormWidget(
            FormRenderModel(
                project_id="17",
                record="1",
                title="Record 1",
                sections=[
                    FormSectionModel(
                        form_name="mr_trus_fzyon_biyopsi",
                        title="MR TRUS Füzyon Biyopsi",
                        fields=[
                            FormFieldModel(
                                "bx_histopatolojik_tani_mr",
                                "mr_trus_fzyon_biyopsi",
                                "Tanı",
                                "dropdown",
                                section_header="Ek Random Biyopsi",
                            ),
                            FormFieldModel(
                                "bx_sag_toplam_kor_mr",
                                "mr_trus_fzyon_biyopsi",
                                "Kor",
                                "text",
                                section_header="Sağ Lob",
                            ),
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QFrame, QLabel

        blocks = form.widget.findChildren(QFrame, "DataEntryFormSubsectionBlock")
        titles = form.widget.findChildren(QLabel, "DataEntryFormSubsectionTitle")

        self.assertEqual(len(blocks), 2)
        self.assertEqual([title.text() for title in titles], ["Ek Random Biyopsi", "Sağ Lob"])

    def test_section_headers_preserve_source_order_and_parent_groups(self) -> None:
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
                            FormFieldModel("record_id", "hasta_bilgileri", "Kayıt no", "text"),
                            FormFieldModel(
                                "dogum_tarihi",
                                "hasta_bilgileri",
                                "Doğum tarihi",
                                DATE_EDITOR,
                                section_header="Demografik Bilgiler",
                            ),
                            FormFieldModel("cinsiyet", "hasta_bilgileri", "Cinsiyet", "text"),
                            FormFieldModel(
                                "telefon",
                                "hasta_bilgileri",
                                "Telefon",
                                "text",
                                section_header="İletişim Bilgileri",
                            ),
                            FormFieldModel("eposta", "hasta_bilgileri", "E-posta", "text"),
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QLabel

        titles = form.widget.findChildren(QLabel, "DataEntryFormSubsectionTitle")

        self.assertEqual(
            list(form.field_rows),
            ["record_id", "dogum_tarihi", "cinsiyet", "telefon", "eposta"],
        )
        self.assertEqual(
            [title.text() for title in titles],
            ["Demografik Bilgiler", "İletişim Bilgileri"],
        )
        self.assertEqual(form.field_rows["record_id"].parentWidget().objectName(), "DataEntryFormSection")
        self.assertIs(form.field_rows["dogum_tarihi"].parentWidget(), form.field_rows["cinsiyet"].parentWidget())
        self.assertIs(form.field_rows["telefon"].parentWidget(), form.field_rows["eposta"].parentWidget())
        self.assertIsNot(form.field_rows["dogum_tarihi"].parentWidget(), form.field_rows["telefon"].parentWidget())
        self.assertEqual(
            form.field_rows["dogum_tarihi"].parentWidget().objectName(),
            "DataEntryFormSubsectionBlock",
        )
        self.assertEqual(
            form.field_rows["telefon"].parentWidget().objectName(),
            "DataEntryFormSubsectionBlock",
        )

    def test_long_combo_options_do_not_force_content_width(self) -> None:
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
                                "long_select",
                                "form",
                                "Uzun seçenek",
                                "dropdown",
                                choices=[
                                    FormChoiceModel(
                                        "1",
                                        "Bu seçenek metni çok uzun ve form genişliğini büyütmemeli",
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        )
        from PySide6.QtWidgets import QComboBox, QSizePolicy

        combo = form.widget.findChild(QComboBox, "DataEntryCombo")

        self.assertIsNotNone(combo)
        self.assertEqual(combo.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Ignored)
        self.assertEqual(
            combo.sizeAdjustPolicy(),
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )

    def test_blank_repeat_section_still_offers_contextual_add_action(self) -> None:
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

        self.assertIsNotNone(form.event_nav)
        self.assertEqual(len(form.event_nav.repeat_buttons), 1)
        blank_action, blank_add_button = form.event_nav.repeat_buttons[0]
        self.assertEqual(blank_action, action)
        self.assertEqual(blank_add_button.parent().property("form_name"), "multiparametrik_mr")
        self.assertTrue(blank_add_button.isEnabled())

        form.set_model(
            FormRenderModel(project_id="17", record="1", title="Record 1", sections=[filled_section]),
            repeat_actions=[action],
        )

        self.assertIsNotNone(form.event_nav)
        self.assertEqual(len(form.event_nav.repeat_buttons), 1)
        filled_action, filled_add_button = form.event_nav.repeat_buttons[0]
        self.assertEqual(filled_action, action)
        self.assertEqual(filled_add_button.parent().property("form_name"), "multiparametrik_mr")
        self.assertTrue(filled_add_button.isEnabled())

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

        self.assertIsNotNone(form.event_nav)
        form.event_nav.target_buttons[0].click()
        form.event_nav.target_buttons[1].click()
        values = form.collect_values()

        self.assertEqual(values["hasta_ad@@event=baseline_arm_1@@repeat=@@instance="], "AB")
        self.assertEqual(values["hasta_ad@@event=followup_arm_1@@repeat=@@instance="], "CD")


if __name__ == "__main__":
    unittest.main()
