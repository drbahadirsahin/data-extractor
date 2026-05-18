import unittest

from identity_registry_client import (
    IdentityRegistryConfig,
    load_identity_registry_config,
    parse_lookup_record_id,
)


class IdentityRegistryClientTests(unittest.TestCase):
    def test_parse_lookup_record_id_from_external_module_response(self):
        payload = {
            "ok": True,
            "project_id": 16,
            "username": "api-user",
            "found": True,
            "match_count": 1,
            "record": "123",
            "matches": [
                {
                    "project_id": 16,
                    "record": "123",
                    "updated_at": "2026-03-17 10:30:00",
                }
            ],
        }
        self.assertEqual(parse_lookup_record_id(payload, "record"), "123")

    def test_parse_lookup_record_id_returns_none_when_not_found(self):
        payload = {"ok": True, "found": False, "match_count": 0, "matches": []}
        self.assertIsNone(parse_lookup_record_id(payload, "record"))

    def test_load_identity_registry_config_uses_external_module_defaults(self):
        config = load_identity_registry_config(
            {
                "identity_registry": {
                    "api_url": "https://redcap.example/api/",
                }
            }
        )
        self.assertEqual(config.api_url, "https://redcap.example/api/")
        self.assertEqual(config.prefix, "tc_hash")
        self.assertEqual(config.lookup_action, "lookup-record-by-tc")
        self.assertEqual(config.create_action, "create-record-by-tc")
        self.assertTrue(config.enabled)
        self.assertTrue(config.can_create)


if __name__ == "__main__":
    unittest.main()
