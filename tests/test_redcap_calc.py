import unittest

from redcap_calc import evaluate_redcap_calc, redcap_calc_field_names


class RedcapCalcTests(unittest.TestCase):
    def test_evaluates_bmi_formula(self) -> None:
        result = evaluate_redcap_calc(
            "round(([hasta_kilo]*10000)/([hasta_boy]*[hasta_boy]),2)",
            {"hasta_kilo": "82", "hasta_boy": "180"},
        )

        self.assertEqual(result, "25.31")

    def test_evaluates_nested_if_formula(self) -> None:
        result = evaluate_redcap_calc(
            (
                "if([bx_primer_gleason]=3,"
                "if([bx_sekonder_gleason]=3,1,if([bx_sekonder_gleason]=4,2,0)),"
                "0)"
            ),
            {"bx_primer_gleason": "3", "bx_sekonder_gleason": "4"},
        )

        self.assertEqual(result, "2")

    def test_returns_blank_until_referenced_values_are_present(self) -> None:
        result = evaluate_redcap_calc(
            "round(([hasta_kilo]*10000)/([hasta_boy]*[hasta_boy]),2)",
            {"hasta_kilo": "82", "hasta_boy": ""},
        )

        self.assertEqual(result, "")

    def test_evaluates_sum_function(self) -> None:
        self.assertEqual(evaluate_redcap_calc("sum([a],[b],[c])", {"a": "1", "b": "2", "c": "3"}), "6")

    def test_collects_checkbox_references(self) -> None:
        self.assertEqual(redcap_calc_field_names("[risk(1)] + [risk(2)]"), {"risk___1", "risk___2"})


if __name__ == "__main__":
    unittest.main()
