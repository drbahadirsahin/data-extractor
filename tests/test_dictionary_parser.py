import csv
import tempfile
import unittest
from pathlib import Path

from dictionary_parser import load_data_dictionary
from project_config import ProjectConfig


class DictionaryParserTests(unittest.TestCase):
    def test_append_fields_are_included_even_if_not_in_target_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "dictionary.csv"
            headers = [
                "Field Label",
                "Variable / Field Name",
                "Field Type",
                "Form Name",
                "Choices, Calculations, OR Slider Labels",
                "Field Note",
                "Text Validation Type OR Show Slider Number",
                "Text Validation Min",
                "Text Validation Max",
                "Field Annotation",
            ]
            rows = [
                {
                    "Field Label": "Hasta Adi",
                    "Variable / Field Name": "hasta_ad",
                    "Field Type": "text",
                    "Form Name": "hasta_bilgileri",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "",
                }
            ]
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)

            config = ProjectConfig(
                project_name="Test",
                dictionary_path=str(csv_path),
                target_forms=[],
                target_fields=["hasta_ad"],
                dictionary_legend={
                    "field_name": "Variable / Field Name",
                    "form_name": "Form Name",
                    "field_type": "Field Type",
                    "field_label": "Field Label",
                    "choices": "Choices, Calculations, OR Slider Labels",
                    "field_note": "Field Note",
                    "text_validation": "Text Validation Type OR Show Slider Number",
                    "text_validation_min": "Text Validation Min",
                    "text_validation_max": "Text Validation Max",
                    "field_annotation": "Field Annotation",
                },
                append_fields=[
                    {
                        "Variable / Field Name": "tc_no",
                        "Form Name": "hasta_bilgileri",
                        "Field Type": "text",
                        "Field Label": "TC Kimlik No",
                        "Choices, Calculations, OR Slider Labels": "",
                        "Field Note": "11 haneli kimlik numarasi",
                        "Text Validation Type OR Show Slider Number": "integer",
                        "Text Validation Min": "",
                        "Text Validation Max": "",
                        "Field Annotation": "",
                    }
                ],
            )

            grouped = load_data_dictionary(config)
            field_names = {field.field_name for fields in grouped.values() for field in fields}
            field_labels = {field.field_name: field.field_label for fields in grouped.values() for field in fields}

            self.assertEqual(field_names, {"hasta_ad", "tc_no"})
            self.assertEqual(field_labels["tc_no"], "TC Kimlik No")

    def test_hidden_fields_are_excluded_from_extraction_even_when_form_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "dictionary.csv"
            headers = [
                "Field Label",
                "Variable / Field Name",
                "Field Type",
                "Form Name",
                "Choices, Calculations, OR Slider Labels",
                "Field Note",
                "Text Validation Type OR Show Slider Number",
                "Text Validation Min",
                "Text Validation Max",
                "Field Annotation",
            ]
            rows = [
                {
                    "Field Label": "Hasta Adi",
                    "Variable / Field Name": "hasta_ad",
                    "Field Type": "text",
                    "Form Name": "hasta_bilgileri",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "",
                },
                {
                    "Field Label": "Gizli Kimlik",
                    "Variable / Field Name": "hidden_identity",
                    "Field Type": "text",
                    "Form Name": "hasta_bilgileri",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "@HIDDEN",
                },
                {
                    "Field Label": "Aciklama",
                    "Variable / Field Name": "notes_display",
                    "Field Type": "notes",
                    "Form Name": "hasta_bilgileri",
                    "Choices, Calculations, OR Slider Labels": "",
                    "Field Note": "",
                    "Text Validation Type OR Show Slider Number": "",
                    "Text Validation Min": "",
                    "Text Validation Max": "",
                    "Field Annotation": "",
                },
            ]
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)

            config = ProjectConfig(
                project_name="Test",
                dictionary_path=str(csv_path),
                target_forms=["hasta_bilgileri"],
                target_fields=[],
                dictionary_legend={
                    "field_name": "Variable / Field Name",
                    "form_name": "Form Name",
                    "field_type": "Field Type",
                    "field_label": "Field Label",
                    "choices": "Choices, Calculations, OR Slider Labels",
                    "field_note": "Field Note",
                    "text_validation": "Text Validation Type OR Show Slider Number",
                    "text_validation_min": "Text Validation Min",
                    "text_validation_max": "Text Validation Max",
                    "field_annotation": "Field Annotation",
                },
            )

            grouped = load_data_dictionary(config)
            field_names = {field.field_name for fields in grouped.values() for field in fields}

            self.assertEqual(field_names, {"hasta_ad"})


if __name__ == "__main__":
    unittest.main()
