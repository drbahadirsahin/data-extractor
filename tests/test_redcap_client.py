import json
import unittest
from unittest.mock import patch

from redcap_client import (
    RedcapAPIError,
    RedcapClient,
    build_redcap_api_url_candidates,
    normalize_redcap_api_url,
    parse_import_record_response,
    parse_form_event_mapping_response,
    infer_user_context,
    parse_instrument_response,
    parse_project_response,
    parse_repeating_events_response,
    parse_repeating_forms_response,
)


class RedcapClientTests(unittest.TestCase):
    def test_normalize_redcap_api_url_appends_api_suffix(self) -> None:
        self.assertEqual(
            normalize_redcap_api_url("https://redcap.example"),
            "https://redcap.example/api/",
        )
        self.assertEqual(
            normalize_redcap_api_url("https://redcap.example/api/"),
            "https://redcap.example/api/",
        )
        self.assertEqual(
            normalize_redcap_api_url("https://redcap.example/api/index.php"),
            "https://redcap.example/api/index.php",
        )
        self.assertEqual(
            build_redcap_api_url_candidates("https://redcap.example/api/"),
            ["https://redcap.example/api/", "https://redcap.example/api/index.php"],
        )

    def test_list_projects_parses_single_project_dict(self) -> None:
        payload = {
            "project_id": 16,
            "project_title": "Prostat Kanseri",
            "is_longitudinal": 0,
        }
        client = RedcapClient("https://redcap.example/api/", "token")
        with patch.object(client, "_post_form", return_value=json.dumps(payload)):
            projects = client.list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].project_id, "16")
        self.assertEqual(projects[0].project_title, "Prostat Kanseri")
        self.assertFalse(projects[0].is_longitudinal)

    def test_list_projects_parses_csv(self) -> None:
        payload = (
            "project_id,project_title,is_longitudinal\n"
            "1,A,0\n"
            "2,B,1\n"
        )
        client = RedcapClient("https://redcap.example/api/", "token")
        with patch.object(client, "_post_form", return_value=payload):
            projects = client.list_projects()

        self.assertEqual([project.project_title for project in projects], ["A", "B"])
        self.assertTrue(projects[1].is_longitudinal)

    def test_parse_project_response_raises_xml_error(self) -> None:
        with self.assertRaises(RedcapAPIError):
            parse_project_response(
                '<?xml version="1.0" encoding="UTF-8"?><hash><error>Bad request</error></hash>'
            )

    def test_parse_instrument_response_returns_labels(self) -> None:
        response = "instrument_name,instrument_label\nform_a,Hasta Bilgileri\nform_b,Laboratuvar\n"
        parsed = parse_instrument_response(response)
        self.assertEqual(parsed["form_a"], "Hasta Bilgileri")
        self.assertEqual(parsed["form_b"], "Laboratuvar")

    def test_parse_instrument_response_supports_json(self) -> None:
        response = json.dumps(
            [
                {"instrument_name": "form_a", "instrument_label": "Hasta Bilgileri"},
                {"form_name": "form_b", "form_label": "Laboratuvar"},
            ]
        )
        parsed = parse_instrument_response(response)
        self.assertEqual(parsed["form_a"], "Hasta Bilgileri")
        self.assertEqual(parsed["form_b"], "Laboratuvar")

    def test_parse_repeating_forms_response_supports_csv_and_json(self) -> None:
        csv_response = (
            "event_name,form_name,custom_form_label\n"
            "event_1,lab_form,\n"
            "event_1,visit_form,\n"
        )
        self.assertEqual(parse_repeating_forms_response(csv_response), ["lab_form", "visit_form"])

        json_response = json.dumps(
            [
                {"event_name": "event_1", "form_name": "lab_form"},
                {"event_name": "event_1", "instrument_name": "visit_form"},
            ]
        )
        self.assertEqual(parse_repeating_forms_response(json_response), ["lab_form", "visit_form"])

    def test_parse_import_record_response_supports_json_and_scalar(self) -> None:
        self.assertEqual(parse_import_record_response('["101","102"]'), ["101", "102"])
        self.assertEqual(parse_import_record_response('{"record_id":"77"}'), ["77"])
        self.assertEqual(parse_import_record_response("55"), ["55"])

    def test_parse_form_event_mapping_response_supports_json(self) -> None:
        response = json.dumps(
            [
                {"form": "hasta_bilgileri", "unique_event_name": "event_1_arm_1"},
                {"form": "tan_laboratuvar_sonucu", "unique_event_name": "event_1_arm_1"},
            ]
        )
        parsed = parse_form_event_mapping_response(response)
        self.assertEqual(parsed["hasta_bilgileri"], ["event_1_arm_1"])
        self.assertEqual(parsed["tan_laboratuvar_sonucu"], ["event_1_arm_1"])

    def test_parse_repeating_events_response_supports_json(self) -> None:
        response = json.dumps(
            [
                {"event_name": "event_1_arm_1", "form_name": ""},
                {"event_name": "event_1_arm_1", "form_name": ""},
                {"unique_event_name": "event_2_arm_1", "form_name": ""},
                {"event_name": "event_3_arm_1", "form_name": "lab_form"},
            ]
        )
        self.assertEqual(parse_repeating_events_response(response), ["event_1_arm_1", "event_2_arm_1"])

    def test_infer_user_context_from_single_user_export(self) -> None:
        context = infer_user_context(
            [
                {
                    "username": "bahadir2",
                    "data_access_group": "Marmara",
                    "api_import": "1",
                    "api_export": "1",
                }
            ]
        )

        self.assertEqual(context.username, "bahadir2")
        self.assertEqual(context.data_access_group, "Marmara")
        self.assertTrue(context.api_import)
        self.assertTrue(context.api_export)

    def test_infer_user_context_avoids_guessing_among_multiple_users(self) -> None:
        context = infer_user_context(
            [
                {"username": "first", "data_access_group": "A"},
                {"username": "second", "data_access_group": "B"},
            ]
        )

        self.assertIsNone(context.username)
        self.assertIsNone(context.data_access_group)

    def test_infer_user_context_uses_current_user_marker(self) -> None:
        context = infer_user_context(
            [
                {"username": "first", "data_access_group": "A"},
                {"username": "second", "data_access_group": "B", "current_user": "1"},
            ]
        )

        self.assertEqual(context.username, "second")
        self.assertEqual(context.data_access_group, "B")


if __name__ == "__main__":
    unittest.main()
