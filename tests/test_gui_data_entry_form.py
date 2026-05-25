import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data_entry_form_model import (
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


if __name__ == "__main__":
    unittest.main()
