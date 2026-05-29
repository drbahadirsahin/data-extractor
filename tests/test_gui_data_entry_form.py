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
from gui.data_entry_form import DataEntryFormWidget


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
        from PySide6.QtWidgets import QListWidget, QStackedWidget

        form_nav = form.widget.findChild(QListWidget, "DataEntryFormNav")
        form_stack = form.widget.findChild(QStackedWidget, "DataEntryFormStack")

        self.assertIsNotNone(form_nav)
        self.assertIsNotNone(form_stack)
        self.assertEqual(form_nav.count(), 2)
        self.assertEqual(form_stack.count(), 2)
        self.assertEqual(form_nav.item(0).text(), "Form A")
        self.assertEqual(form_nav.item(1).text(), "Form B\n1/1 alan dolu")
        self.assertEqual(form_nav.currentRow(), 1)
        self.assertEqual(form.current_section().form_name, "b")
        self.assertNotIn("a1", form.editor_widgets)
        self.assertIn("b1", form.editor_widgets)

        form_nav.setCurrentRow(0)

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
        from PySide6.QtWidgets import QListWidget

        form_nav = form.widget.findChild(QListWidget, "DataEntryFormNav")

        self.assertEqual([form_nav.item(index).text() for index in range(form_nav.count())], [
            "Başlangıç",
            "Hasta Bilgileri",
            "Laboratuvar",
            "İzlem",
            "Hasta Bilgileri\n1/1 alan dolu",
        ])
        self.assertEqual(form.current_section().event_id, "followup_arm_1")

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
                                context_key="hasta_ad@@event=baseline_arm_1@@instance=",
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
                                context_key="hasta_ad@@event=followup_arm_1@@instance=",
                            )
                        ],
                    ),
                ],
            )
        )

        form.form_nav.setCurrentRow(1)
        values = form.collect_values()

        self.assertEqual(values["hasta_ad@@event=baseline_arm_1@@instance="], "AB")
        self.assertEqual(values["hasta_ad@@event=followup_arm_1@@instance="], "CD")


if __name__ == "__main__":
    unittest.main()
