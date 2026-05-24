import tempfile
import unittest
from pathlib import Path

from data_entry_store import DataEntryStore, RedcapDataValue
from dynamic_sql import DynamicSqlError, DynamicSqlEvaluator, translate_dynamic_sql


COMPLEX_MR_LESION_SQL = """
SELECT CONCAT(
    IF(r_data.instance IS NULL, 1, r_data.instance),
    '. ',
    GROUP_CONCAT(
        CONCAT(
            CASE
                WHEN r_data.field_name = 'mr_tarih_secimi' THEN 'MR Tarihi'
                WHEN r_data.field_name = 'lezyon_tarafi' THEN 'Taraf'
                WHEN r_data.field_name = 'lezyon_yerlesim' THEN 'Yerleşim'
                WHEN r_data.field_name = 'lezyon_bolge' THEN 'Bölge'
                WHEN r_data.field_name = 'lezyon_boyutu' THEN 'Boyut'
                WHEN r_data.field_name = 'lezyon_pirads' THEN 'PiRADS'
                ELSE r_data.field_name
            END,
            ': ',
            CASE
                WHEN r_data.field_name = 'mr_tarih_secimi' THEN r_data.value
                WHEN r_data.field_name = 'lezyon_pirads' THEN r_data.value
                WHEN r_data.field_name = 'lezyon_tarafi' THEN
                    CASE
                        WHEN r_data.value = '1' THEN 'Sağ'
                        WHEN r_data.value = '2' THEN 'Sol'
                        ELSE NULL
                    END
                WHEN r_data.field_name = 'lezyon_yerlesim' THEN
                    CASE
                        WHEN r_data.value = '1' THEN 'Anterior'
                        WHEN r_data.value = '2' THEN 'Posterior'
                        ELSE NULL
                    END
                WHEN r_data.field_name = 'lezyon_bolge' THEN
                    CASE
                        WHEN r_data.value = '1' THEN 'Apeks'
                        WHEN r_data.value = '2' THEN 'Mid'
                        WHEN r_data.value = '3' THEN 'Base'
                        ELSE NULL
                    END
                WHEN r_data.field_name = 'lezyon_boyutu' THEN
                    CASE
                        WHEN r_data.value = '1' THEN '0 - 1'
                        WHEN r_data.value = '2' THEN '1.1 - 2'
                        WHEN r_data.value = '3' THEN '2.1 - 3'
                        WHEN r_data.value = '4' THEN '3.1 - 4'
                        WHEN r_data.value = '5' THEN '>4'
                        ELSE NULL
                    END
                ELSE NULL
            END
        )
        SEPARATOR ' | '
    )
) AS value
FROM redcap_data AS r_data
WHERE r_data.project_id = 16
  AND r_data.event_id = 44
  AND r_data.record = [record-name]
  AND r_data.field_name IN (
    'mr_tarih_secimi',
    'lezyon_tarafi',
    'lezyon_yerlesim',
    'lezyon_bolge',
    'lezyon_boyutu',
    'lezyon_pirads'
  )
GROUP BY r_data.instance
"""


class DynamicSqlTests(unittest.TestCase):
    def test_translates_record_placeholder_to_parameter(self) -> None:
        sql, params = translate_dynamic_sql(
            "select value from redcap_data where project_id=16 and record=[record-name]",
            record="1 OR 1=1",
        )

        self.assertEqual(sql, "select value from redcap_data where project_id=16 and record=?")
        self.assertEqual(params, ["1 OR 1=1"])

    def test_evaluates_simple_redcap_data_sql_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="16",
                        event_id="",
                        record="12",
                        field_name="mr_trus_bx_tarihi",
                        value="2026-05-20",
                    ),
                    RedcapDataValue(
                        project_id="16",
                        event_id="",
                        record="99",
                        field_name="mr_trus_bx_tarihi",
                        value="2099-01-01",
                    ),
                ]
            )

            options = DynamicSqlEvaluator(store).evaluate(
                "select value from redcap_data where project_id=16 and field_name='mr_trus_bx_tarihi' and record=[record-name]",
                record="12",
            )

            self.assertEqual([(item.value, item.label) for item in options], [("2026-05-20", "2026-05-20")])

    def test_record_placeholder_is_parameterized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue(
                        project_id="16",
                        event_id="",
                        record="12",
                        field_name="tani_mr_tarihi",
                        value="2026-05-20",
                    )
                ]
            )

            options = DynamicSqlEvaluator(store).evaluate(
                "select value from redcap_data where project_id=16 and field_name='tani_mr_tarihi' and record=[record-name]",
                record="12 OR 1=1",
            )

            self.assertEqual(options, [])

    def test_evaluates_mysql_concat_if_and_group_concat_separator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()
            store.upsert_remote_values(
                [
                    RedcapDataValue("16", "44", "12", "mr_tarih_secimi", "2026-05-20", instance="1"),
                    RedcapDataValue("16", "44", "12", "lezyon_tarafi", "1", instance="1"),
                    RedcapDataValue("16", "44", "12", "lezyon_yerlesim", "2", instance="1"),
                    RedcapDataValue("16", "44", "12", "lezyon_bolge", "3", instance="1"),
                    RedcapDataValue("16", "44", "12", "lezyon_boyutu", "4", instance="1"),
                    RedcapDataValue("16", "44", "12", "lezyon_pirads", "5", instance="1"),
                    RedcapDataValue("16", "44", "12", "mr_tarih_secimi", "2026-06-01", instance="2"),
                    RedcapDataValue("16", "44", "12", "lezyon_tarafi", "2", instance="2"),
                    RedcapDataValue("16", "44", "12", "lezyon_pirads", "4", instance="2"),
                ]
            )

            options = DynamicSqlEvaluator(store).evaluate(COMPLEX_MR_LESION_SQL, record="12")

            self.assertEqual(len(options), 2)
            self.assertIn("1. ", options[0].value)
            self.assertIn("MR Tarihi: 2026-05-20", options[0].value)
            self.assertIn("Taraf: Sağ", options[0].value)
            self.assertIn("Yerleşim: Posterior", options[0].value)
            self.assertIn("Bölge: Base", options[0].value)
            self.assertIn("Boyut: 3.1 - 4", options[0].value)
            self.assertIn("PiRADS: 5", options[0].value)
            self.assertIn(" | ", options[0].value)
            self.assertIn("2. ", options[1].value)
            self.assertIn("Taraf: Sol", options[1].value)

    def test_rejects_non_select_sql(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()

            with self.assertRaises(DynamicSqlError):
                DynamicSqlEvaluator(store).evaluate(
                    "delete from redcap_data where record=[record-name]",
                    record="12",
                )

    def test_rejects_queries_outside_redcap_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DataEntryStore(Path(temp_dir) / "data_entry.sqlite3")
            store.initialize()

            with self.assertRaises(DynamicSqlError):
                DynamicSqlEvaluator(store).evaluate(
                    "select name from sqlite_master",
                    record="12",
                )


if __name__ == "__main__":
    unittest.main()
