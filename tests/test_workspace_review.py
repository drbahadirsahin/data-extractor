import unittest

from run_extraction import ExtractionFieldResult, ExtractionResponse
from workspace_extraction import PatientExtractionResult
from workspace_review import (
    build_patient_result_label,
    count_patient_result_status,
    parse_review_value,
    serialize_review_value,
)


class WorkspaceReviewTests(unittest.TestCase):
    def test_serialize_and_parse_review_value(self) -> None:
        self.assertEqual(serialize_review_value({"a": 1}), '{"a": 1}')
        self.assertEqual(parse_review_value('{"a": 1}'), {"a": 1})
        self.assertEqual(parse_review_value("42"), 42)
        self.assertEqual(parse_review_value("merhaba"), "merhaba")
        self.assertIsNone(parse_review_value("   "))

    def test_patient_result_label_includes_status_counts(self) -> None:
        result = PatientExtractionResult(
            queue_label="Hasta A",
            patient_mode="new",
            identifier_type=None,
            identifier_value=None,
            documents=["a.pdf"],
            document_results=[],
            merged_response=ExtractionResponse(
                project_name="Demo",
                results=[
                    ExtractionFieldResult(field_name="hasta_ad", status="found", final_value="Ali"),
                    ExtractionFieldResult(field_name="psa", status="uncertain", needs_review=True),
                ],
            ),
        )

        self.assertEqual(count_patient_result_status(result), (1, 1, 2))
        label = build_patient_result_label(result)
        self.assertIn("Hasta A", label)
        self.assertIn("1/2 found", label)
        self.assertIn("1 review", label)


if __name__ == "__main__":
    unittest.main()
