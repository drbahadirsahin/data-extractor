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


if __name__ == "__main__":
    unittest.main()
