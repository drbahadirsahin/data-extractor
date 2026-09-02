import os
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gui.override_editor import build_override_number_control, edit_override_payload


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class GuiOverrideEditorTests(unittest.TestCase):
    def test_number_control_uses_visible_step_buttons_and_preserves_readable_value(self) -> None:
        app = get_qapplication()
        from PySide6.QtWidgets import QAbstractSpinBox

        control = build_override_number_control(
            minimum=1,
            maximum=50,
            value=7,
            accessible_name="En fazla aday",
        )
        control.widget.show()
        app.processEvents()

        self.assertEqual(control.spin_box.buttonSymbols(), QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.assertEqual(control.spin_box.text(), "7")
        self.assertEqual(control.up_button.text(), "▲")
        self.assertEqual(control.down_button.text(), "▼")
        self.assertTrue(control.up_button.isVisible())
        self.assertTrue(control.down_button.isVisible())

        control.up_button.click()
        self.assertEqual(control.value(), 8)
        control.down_button.click()
        self.assertEqual(control.value(), 7)

        control.set_enabled(False)
        self.assertFalse(control.widget.isEnabled())
        self.assertFalse(control.spin_box.isEnabled())
        self.assertFalse(control.up_button.isEnabled())
        self.assertEqual(control.spin_box.text(), "7")

        control.set_enabled(True)
        self.assertTrue(control.spin_box.isEnabled())
        self.assertEqual(control.spin_box.text(), "7")
        control.widget.close()

    def test_override_dialog_toggles_and_saves_both_number_controls(self) -> None:
        get_qapplication()
        from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QSpinBox

        observed: dict[str, bool] = {}

        def interact_with_dialog(dialog: QDialog) -> int:
            max_toggle = dialog.findChild(QCheckBox, "OverrideMaxCandidatesEnabled")
            length_toggle = dialog.findChild(QCheckBox, "OverrideLimitLengthEnabled")
            self.assertIsNotNone(max_toggle)
            self.assertIsNotNone(length_toggle)

            spins = dialog.findChildren(QSpinBox, "OverrideNumberSpinBox")
            self.assertEqual(len(spins), 2)
            by_name = {spin.accessibleName(): spin for spin in spins}
            max_spin = by_name["En fazla aday"]
            length_spin = by_name["En fazla karakter"]

            observed["max_initially_disabled"] = not max_spin.isEnabled()
            observed["length_initially_disabled"] = not length_spin.isEnabled()
            max_toggle.setChecked(True)
            length_toggle.setChecked(True)
            observed["max_enabled_after_toggle"] = max_spin.isEnabled()
            observed["length_enabled_after_toggle"] = length_spin.isEnabled()
            max_spin.setValue(9)
            length_spin.setValue(321)

            button_box = dialog.findChild(QDialogButtonBox)
            self.assertIsNotNone(button_box)
            button_box.accepted.emit()
            return int(QDialog.DialogCode.Accepted)

        with patch.object(QDialog, "exec", new=interact_with_dialog):
            result = edit_override_payload(
                parent=None,
                title="Alan için kurallar",
                subject_label="Yan Etki",
                payload={"post_processing": [["trim"]]},
                language="tr",
            )

        self.assertEqual(
            observed,
            {
                "max_initially_disabled": True,
                "length_initially_disabled": True,
                "max_enabled_after_toggle": True,
                "length_enabled_after_toggle": True,
            },
        )
        self.assertEqual(
            result,
            {
                "max_candidates": 9,
                "post_processing": [["trim"], ["limit_output_length", 321]],
            },
        )

    def test_number_control_style_has_explicit_light_and_disabled_states(self) -> None:
        from gui.clinical_styles import CLINICAL_OVERRIDE_NUMBER_STYLE

        self.assertIn("QSpinBox#OverrideNumberSpinBox", CLINICAL_OVERRIDE_NUMBER_STYLE)
        self.assertIn("background: #ffffff", CLINICAL_OVERRIDE_NUMBER_STYLE)
        self.assertIn("color: #0f172a", CLINICAL_OVERRIDE_NUMBER_STYLE)
        self.assertIn("QToolButton#OverrideNumberStepUp", CLINICAL_OVERRIDE_NUMBER_STYLE)
        self.assertIn("QToolButton#OverrideNumberStepDown", CLINICAL_OVERRIDE_NUMBER_STYLE)
        self.assertIn("QSpinBox#OverrideNumberSpinBox:disabled", CLINICAL_OVERRIDE_NUMBER_STYLE)


if __name__ == "__main__":
    unittest.main()
