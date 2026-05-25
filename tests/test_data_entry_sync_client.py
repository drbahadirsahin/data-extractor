import json
import unittest
from unittest.mock import patch

from data_entry_sync_client import (
    DataEntrySyncClient,
    DataEntrySyncConfig,
    DataEntrySyncError,
    encode_list_param,
    load_data_entry_sync_config,
    parse_external_module_response,
    parse_identity_hash_map_response,
    parse_record_data_response,
    parse_sync_manifest_response,
)


class DataEntrySyncClientTests(unittest.TestCase):
    def test_load_config_uses_identity_registry_prefix_and_api_url_defaults(self) -> None:
        config = load_data_entry_sync_config(
            {
                "identity_registry": {
                    "api_url": "https://redcap.example/api/",
                    "prefix": "tc_hash",
                }
            }
        )

        self.assertTrue(config.enabled)
        self.assertEqual(config.api_url, "https://redcap.example/api/")
        self.assertEqual(config.prefix, "tc_hash")
        self.assertEqual(config.manifest_action, "get-sync-manifest")

    def test_encode_list_param_uses_json_array(self) -> None:
        self.assertEqual(encode_list_param(["1", "2"]), '["1", "2"]')
        self.assertIsNone(encode_list_param([]))

    def test_client_posts_manifest_action(self) -> None:
        client = DataEntrySyncClient(
            DataEntrySyncConfig(api_url="https://redcap.example/api/", prefix="tc_hash"),
            api_token="secret",
        )
        with patch.object(
            client,
            "_post_external_module",
            return_value={
                "project_id": "17",
                "records": [{"record": "1", "sync_updated_at": "2026-05-24 10:31:00"}],
            },
        ) as post:
            response = client.get_sync_manifest(since="2026-05-23 00:00:00")

        payload = post.call_args.args[0]
        self.assertEqual(payload["action"], "get-sync-manifest")
        self.assertEqual(payload["since"], "2026-05-23 00:00:00")
        self.assertEqual(response.records[0].record, "1")

    def test_client_posts_record_data_filters(self) -> None:
        client = DataEntrySyncClient(
            DataEntrySyncConfig(api_url="https://redcap.example/api/", prefix="tc_hash"),
            api_token="secret",
        )
        with patch.object(
            client,
            "_post_external_module",
            return_value={"project_id": "17", "records": []},
        ) as post:
            client.get_record_data(
                records=["1", "2"],
                fields=["hasta_ad"],
                events=["event_1_arm_1"],
                since="2026-05-23 00:00:00",
            )

        payload = post.call_args.args[0]
        self.assertEqual(payload["action"], "get-record-data")
        self.assertEqual(json.loads(payload["records"]), ["1", "2"])
        self.assertEqual(json.loads(payload["fields"]), ["hasta_ad"])
        self.assertEqual(json.loads(payload["events"]), ["event_1_arm_1"])
        self.assertEqual(payload["since"], "2026-05-23 00:00:00")

    def test_client_posts_identity_hash_action(self) -> None:
        client = DataEntrySyncClient(
            DataEntrySyncConfig(api_url="https://redcap.example/api/", prefix="tc_hash"),
            api_token="secret",
        )
        with patch.object(
            client,
            "_post_external_module",
            return_value={"project_id": "17", "rows": [{"record": "1", "identity_hash": "hash"}]},
        ) as post:
            response = client.get_identity_hash_map()

        self.assertEqual(post.call_args.args[0]["action"], "get-identity-hash-map")
        self.assertEqual(response.entries[0].tc_hash, "hash")

    def test_parse_external_module_error_response_raises(self) -> None:
        with self.assertRaises(DataEntrySyncError):
            parse_external_module_response('{"error":"Yetkisiz"}')

    def test_parse_sync_manifest_uses_sync_updated_at_for_remote_updated_at(self) -> None:
        response = parse_sync_manifest_response(
            {
                "project_id": "17",
                "dag": "marmara",
                "identity_hash_updated_at": "2026-05-24 10:31:00",
                "records": [
                    {
                        "record": "123",
                        "data_access_group_unique_name": "marmara",
                        "record_last_modified_at": "2026-05-24 10:25:00",
                        "identity_hash_updated_at": "2026-05-24 10:31:00",
                        "sync_updated_at": "2026-05-24 10:31:00",
                    }
                ],
            }
        )

        self.assertEqual(response.project_id, "17")
        self.assertEqual(response.dag_unique_name, "marmara")
        self.assertEqual(response.records[0].record, "123")
        self.assertEqual(response.records[0].dag_unique_name, "marmara")
        self.assertEqual(response.records[0].remote_updated_at, "2026-05-24 10:31:00")
        self.assertEqual(response.records[0].record_last_modified_at, "2026-05-24 10:25:00")
        self.assertEqual(response.records[0].identity_hash_updated_at, "2026-05-24 10:31:00")

    def test_parse_sync_manifest_computes_sync_updated_at_when_missing(self) -> None:
        response = parse_sync_manifest_response(
            {
                "project_id": "17",
                "records": [
                    {
                        "record": "123",
                        "record_last_modified_at": "2026-05-24 10:25:00",
                        "identity_hash_updated_at": "2026-05-24 10:31:00",
                    }
                ],
            }
        )

        self.assertEqual(response.records[0].remote_updated_at, "2026-05-24 10:31:00")

    def test_parse_record_data_flattens_record_rows(self) -> None:
        response = parse_record_data_response(
            {
                "project_id": "17",
                "records": [
                    {
                        "record": "123",
                        "data_access_group_unique_name": "marmara",
                        "record_last_modified_at": "2026-05-24 10:25:00",
                        "rows": [
                            {
                                "event_id": "44",
                                "field_name": "hasta_ad",
                                "value": "AB",
                                "instance": "",
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(response.project_id, "17")
        self.assertEqual(len(response.values), 1)
        value = response.values[0]
        self.assertEqual(value.project_id, "17")
        self.assertEqual(value.event_id, "44")
        self.assertEqual(value.record, "123")
        self.assertEqual(value.field_name, "hasta_ad")
        self.assertEqual(value.value, "AB")
        self.assertEqual(value.dag_unique_name, "marmara")
        self.assertEqual(value.remote_updated_at, "2026-05-24 10:25:00")

    def test_parse_record_data_supports_flat_rows(self) -> None:
        response = parse_record_data_response(
            {
                "project_id": "17",
                "rows": [
                    {
                        "record": "123",
                        "field_name": "hasta_ad",
                        "value": "AB",
                    }
                ],
            }
        )

        self.assertEqual(len(response.values), 1)
        self.assertEqual(response.values[0].record, "123")

    def test_parse_record_data_supports_wide_redcap_records(self) -> None:
        response = parse_record_data_response(
            {
                "project_id": "17",
                "records": [
                    {
                        "record_id": "123",
                        "redcap_event_name": "baseline_arm_1",
                        "data_access_group_unique_name": "marmara",
                        "record_last_modified_at": "2026-05-24 10:25:00",
                        "hasta_ad": "AHMET",
                        "hasta_soyad": "YILMAZ",
                        "risk___1": "1",
                    }
                ],
            }
        )

        by_field = {item.field_name: item for item in response.values}
        self.assertEqual(len(response.values), 3)
        self.assertEqual(by_field["hasta_ad"].project_id, "17")
        self.assertEqual(by_field["hasta_ad"].record, "123")
        self.assertEqual(by_field["hasta_ad"].event_id, "baseline_arm_1")
        self.assertEqual(by_field["hasta_ad"].value, "AHMET")
        self.assertEqual(by_field["hasta_ad"].dag_unique_name, "marmara")
        self.assertEqual(by_field["risk___1"].value, "1")

    def test_parse_identity_hash_map_accepts_identity_hash_key(self) -> None:
        response = parse_identity_hash_map_response(
            {
                "project_id": "17",
                "rows": [
                    {
                        "record": "123",
                        "identity_hash": "hashed-tc",
                        "identity_hash_updated_at": "2026-05-24 10:31:00",
                    }
                ],
            }
        )

        self.assertEqual(response.project_id, "17")
        self.assertEqual(len(response.entries), 1)
        self.assertEqual(response.entries[0].project_id, "17")
        self.assertEqual(response.entries[0].record, "123")
        self.assertEqual(response.entries[0].tc_hash, "hashed-tc")
        self.assertEqual(response.entries[0].remote_updated_at, "2026-05-24 10:31:00")


if __name__ == "__main__":
    unittest.main()
