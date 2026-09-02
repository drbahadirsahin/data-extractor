from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gui.workspace_page import WorkspacePage


class WorkspacePatientQueueTests(unittest.TestCase):
    def make_page(self, *, bundle=object()) -> WorkspacePage:
        page = WorkspacePage.__new__(WorkspacePage)
        page.bundle = bundle
        page.language = "en"
        page.selected_form_names = {"sample_form"}
        page.selected_field_names = {"sample_field"}
        page.patient_queue_items = []
        page.ensure_tc_identifier_append_field = Mock()
        page.refresh_patient_queue_list = Mock()
        return page

    def test_enqueue_rejects_missing_bundle(self) -> None:
        page = self.make_page(bundle=None)

        success, message = page.enqueue_patient_documents(
            queue_label="Sample queue",
            patient_mode="new",
            identifier_type=None,
            identifier_value=None,
            documents=["/tmp/sample-a.pdf"],
        )

        self.assertFalse(success)
        self.assertEqual(
            message,
            "Save at least one REDCap project token in setup before using the workspace.",
        )
        self.assertEqual(page.patient_queue_items, [])
        page.refresh_patient_queue_list.assert_not_called()

    def test_enqueue_rejects_missing_documents(self) -> None:
        page = self.make_page()

        success, message = page.enqueue_patient_documents(
            queue_label="Sample queue",
            patient_mode="new",
            identifier_type=None,
            identifier_value=None,
            documents=["", "   "],
        )

        self.assertFalse(success)
        self.assertEqual(message, "Add at least one document for this patient first.")
        page.ensure_tc_identifier_append_field.assert_not_called()
        page.refresh_patient_queue_list.assert_not_called()

    def test_enqueue_rejects_existing_patient_without_identifier(self) -> None:
        page = self.make_page()

        success, message = page.enqueue_patient_documents(
            queue_label="Sample queue",
            patient_mode="existing",
            identifier_type="record_id",
            identifier_value="   ",
            documents=["/tmp/sample-a.pdf"],
        )

        self.assertFalse(success)
        self.assertEqual(message, "An identifier value is required for an existing patient.")
        page.ensure_tc_identifier_append_field.assert_not_called()
        page.refresh_patient_queue_list.assert_not_called()

    def test_enqueue_rejects_unsupported_patient_mode(self) -> None:
        page = self.make_page()

        success, message = page.enqueue_patient_documents(
            queue_label="Sample queue",
            patient_mode="unsupported",
            identifier_type=None,
            identifier_value=None,
            documents=["/tmp/sample-a.pdf"],
        )

        self.assertFalse(success)
        self.assertIn("unsupported", message)
        self.assertEqual(page.patient_queue_items, [])
        page.refresh_patient_queue_list.assert_not_called()

    def test_enqueue_new_patient_preserves_document_order_and_removes_duplicates(self) -> None:
        page = self.make_page()
        config_snapshot = SimpleNamespace(project_name="Sample project")

        with patch(
            "gui.workspace_page.build_scoped_project_config",
            return_value=config_snapshot,
        ) as build_snapshot:
            success, message = page.enqueue_patient_documents(
                queue_label="",
                patient_mode="new",
                identifier_type="record_id",
                identifier_value="ignored",
                documents=[
                    "/tmp/sample-b.pdf",
                    "/tmp/sample-a.png",
                    "/tmp/sample-b.pdf",
                    "/tmp/sample-c.txt",
                ],
            )

        self.assertTrue(success)
        self.assertEqual(message, "")
        page.ensure_tc_identifier_append_field.assert_called_once_with()
        build_snapshot.assert_called_once_with(
            page.bundle,
            {"sample_form"},
            {"sample_field"},
        )
        page.refresh_patient_queue_list.assert_called_once_with()
        self.assertEqual(len(page.patient_queue_items), 1)
        job = page.patient_queue_items[0]
        self.assertEqual(job.queue_label, "New patient | 3 document(s)")
        self.assertEqual(job.patient_mode, "new")
        self.assertIsNone(job.identifier_type)
        self.assertIsNone(job.identifier_value)
        self.assertEqual(
            job.documents,
            ["/tmp/sample-b.pdf", "/tmp/sample-a.png", "/tmp/sample-c.txt"],
        )
        self.assertIs(job.config_snapshot, config_snapshot)

    def test_enqueue_existing_patient_uses_trimmed_values_and_custom_label(self) -> None:
        page = self.make_page()
        config_snapshot = SimpleNamespace(project_name="Sample project")

        with patch(
            "gui.workspace_page.build_scoped_project_config",
            return_value=config_snapshot,
        ):
            success, message = page.enqueue_patient_documents(
                queue_label="  Review batch  ",
                patient_mode=" existing ",
                identifier_type=" tc_kimlik_no ",
                identifier_value=" sample-id-001 ",
                documents=["/tmp/sample-a.pdf"],
            )

        self.assertTrue(success)
        self.assertEqual(message, "")
        page.ensure_tc_identifier_append_field.assert_not_called()
        page.refresh_patient_queue_list.assert_called_once_with()
        job = page.patient_queue_items[0]
        self.assertEqual(job.queue_label, "Review batch")
        self.assertEqual(job.patient_mode, "existing")
        self.assertEqual(job.identifier_type, "tc_kimlik_no")
        self.assertEqual(job.identifier_value, "sample-id-001")
        self.assertEqual(job.documents, ["/tmp/sample-a.pdf"])


if __name__ == "__main__":
    unittest.main()
