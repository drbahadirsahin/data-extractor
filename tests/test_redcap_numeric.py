import unittest

from redcap_numeric import normalize_redcap_numeric_text


class RedcapNumericTests(unittest.TestCase):
    def test_decimal_comma_is_normalized_to_dot_for_number_fields(self) -> None:
        self.assertEqual(normalize_redcap_numeric_text("14,46", "number"), "14.46")
        self.assertEqual(normalize_redcap_numeric_text("14.46", "number"), "14.46")
        self.assertEqual(normalize_redcap_numeric_text(",5", "number"), "0.5")
        self.assertEqual(normalize_redcap_numeric_text("0014,460", "number_3dp"), "14.460")

    def test_integer_values_are_normalized_without_decimal_separator(self) -> None:
        self.assertEqual(normalize_redcap_numeric_text("+0014", "integer"), "14")
        self.assertEqual(normalize_redcap_numeric_text("-000", "integer"), "0")
        self.assertEqual(normalize_redcap_numeric_text(0, "integer"), "0")

    def test_mixed_separators_are_left_for_validation_instead_of_guessed(self) -> None:
        self.assertEqual(normalize_redcap_numeric_text("1.234,56", "number"), "1.234,56")
        self.assertEqual(normalize_redcap_numeric_text("1,234.56", "number"), "1,234.56")


if __name__ == "__main__":
    unittest.main()
