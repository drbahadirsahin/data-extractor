import unittest

from run_extraction import ExtractionFieldResult, ExtractionResponse
from workspace_extraction import merge_document_responses


class WorkspaceExtractionTests(unittest.TestCase):
    def test_merge_document_responses_marks_disagreement_for_review(self) -> None:
        response_a = ExtractionResponse(
            project_name="Demo",
            results=[
                ExtractionFieldResult(
                    field_name="psa",
                    form_name="lab",
                    status="found",
                    final_value="4.2",
                    confidence=0.9,
                )
            ],
        )
        response_b = ExtractionResponse(
            project_name="Demo",
            results=[
                ExtractionFieldResult(
                    field_name="psa",
                    form_name="lab",
                    status="found",
                    final_value="5.1",
                    confidence=0.7,
                )
            ],
        )

        merged = merge_document_responses(project_name="Demo", responses=[response_a, response_b])

        self.assertEqual(len(merged.results), 1)
        self.assertEqual(merged.results[0].status, "conflict")
        self.assertTrue(merged.results[0].needs_review)
        self.assertIn("multiple_documents_disagree", merged.results[0].review_reasons)
        self.assertEqual(merged.results[0].final_value, "4.2")

    def test_merge_document_responses_keeps_highest_confidence_found_value(self) -> None:
        response_a = ExtractionResponse(
            project_name="Demo",
            results=[
                ExtractionFieldResult(
                    field_name="hasta_ad",
                    form_name="demographics",
                    status="found",
                    final_value="Ali",
                    confidence=0.95,
                )
            ],
        )
        response_b = ExtractionResponse(
            project_name="Demo",
            results=[
                ExtractionFieldResult(
                    field_name="hasta_ad",
                    form_name="demographics",
                    status="uncertain",
                    final_value="Ali",
                    confidence=0.40,
                    needs_review=True,
                    review_reasons=["low_confidence"],
                )
            ],
        )

        merged = merge_document_responses(project_name="Demo", responses=[response_a, response_b])

        self.assertEqual(merged.results[0].status, "found")
        self.assertEqual(merged.results[0].final_value, "Ali")
        self.assertTrue(merged.results[0].needs_review)
        self.assertIn("low_confidence", merged.results[0].review_reasons)


if __name__ == "__main__":
    unittest.main()
