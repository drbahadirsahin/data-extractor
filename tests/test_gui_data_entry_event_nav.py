import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from data_entry_form_model import FormFieldModel, FormRenderModel, FormSectionModel
from gui.data_entry_event_nav import DataEntryEventNav, build_event_nav_model


def get_qapplication():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def record_model() -> FormRenderModel:
    return FormRenderModel(
        project_id="17",
        record="96-3",
        title="96-3 Ahmet Yılmaz",
        sections=[
            FormSectionModel(
                form_name="hasta_bilgileri",
                title="Hasta Bilgileri",
                event_id="baseline_arm_1",
                event_label="Başlangıç",
                fields=[
                    FormFieldModel(
                        "hasta_ad",
                        "hasta_bilgileri",
                        "Ad",
                        "text",
                        "Ahmet",
                        required=True,
                    )
                ],
            ),
            FormSectionModel(
                form_name="laboratuvar",
                title="Laboratuvar",
                event_id="baseline_arm_1",
                event_label="Başlangıç",
                repeat_instrument="laboratuvar",
                instance="1",
                fields=[
                    FormFieldModel("psa", "laboratuvar", "PSA", "text", "4.2", required=True)
                ],
            ),
            FormSectionModel(
                form_name="laboratuvar",
                title="Laboratuvar",
                event_id="baseline_arm_1",
                event_label="Başlangıç",
                repeat_instrument="laboratuvar",
                instance="2",
                fields=[
                    FormFieldModel("psa", "laboratuvar", "PSA", "text", "", required=True)
                ],
            ),
            FormSectionModel(
                form_name="biyopsi",
                title="Klasik Biyopsi",
                event_id="biopsy_arm_1",
                event_label="Klasik Biyopsi #1",
                instance="1",
                fields=[FormFieldModel("tarih", "biyopsi", "Tarih", "date", "2026-05-10")],
            ),
            FormSectionModel(
                form_name="patoloji",
                title="Patoloji",
                event_id="biopsy_arm_1",
                event_label="Klasik Biyopsi #1",
                instance="1",
                fields=[FormFieldModel("sonuc", "patoloji", "Sonuç", "text", "Benign")],
            ),
            FormSectionModel(
                form_name="biyopsi",
                title="Klasik Biyopsi",
                event_id="biopsy_arm_1",
                event_label="Klasik Biyopsi #2",
                instance="2",
                fields=[FormFieldModel("tarih", "biyopsi", "Tarih", "date", "")],
            ),
            FormSectionModel(
                form_name="patoloji",
                title="Patoloji",
                event_id="biopsy_arm_1",
                event_label="Klasik Biyopsi #2",
                instance="2",
                fields=[FormFieldModel("sonuc", "patoloji", "Sonuç", "text", "")],
            ),
        ],
    )


def repeat_actions():
    return [
        {
            "kind": "event",
            "event_id": "biopsy_arm_1",
            "event_label": "Klasik Biyopsi",
            "label": "Event: Klasik Biyopsi #3",
        },
        {
            "kind": "form",
            "form_name": "laboratuvar",
            "form_label": "Laboratuvar",
            "event_id": "baseline_arm_1",
            "label": "Form: Başlangıç / Laboratuvar #3",
        },
    ]


class DataEntryEventNavModelTests(unittest.TestCase):
    def test_one_group_per_event_with_event_instances_and_inline_form_repeats(self) -> None:
        nav_model = build_event_nav_model(record_model(), repeat_actions())

        self.assertEqual([group.key for group in nav_model.groups], ["baseline_arm_1", "biopsy_arm_1"])
        baseline, biopsy = nav_model.groups
        self.assertEqual(baseline.label, "Başlangıç")
        self.assertEqual([item.instance for item in baseline.instances], [""])
        self.assertEqual(
            [form.form_name for form in baseline.instances[0].forms],
            ["hasta_bilgileri", "laboratuvar"],
        )
        laboratory = baseline.instances[0].forms[1]
        self.assertEqual([target.instance for target in laboratory.targets], ["1", "2"])
        self.assertEqual(laboratory.repeat_actions, [repeat_actions()[1]])

        self.assertEqual(biopsy.label, "Klasik Biyopsi")
        self.assertEqual([item.instance for item in biopsy.instances], ["1", "2"])
        self.assertEqual(
            [[form.form_name for form in item.forms] for item in biopsy.instances],
            [["biyopsi", "patoloji"], ["biyopsi", "patoloji"]],
        )
        self.assertEqual(biopsy.repeat_actions, [repeat_actions()[0]])

    def test_explicit_metadata_order_reorders_groups_and_each_instances_forms(self) -> None:
        nav_model = build_event_nav_model(
            record_model(),
            repeat_actions(),
            event_order=["biopsy_arm_1", "baseline_arm_1"],
            form_order=["patoloji", "biyopsi", "laboratuvar", "hasta_bilgileri"],
        )

        self.assertEqual([group.key for group in nav_model.groups], ["biopsy_arm_1", "baseline_arm_1"])
        self.assertEqual(
            [[form.form_name for form in item.forms] for item in nav_model.groups[0].instances],
            [["patoloji", "biyopsi"], ["patoloji", "biyopsi"]],
        )
        self.assertEqual(
            [form.form_name for form in nav_model.groups[1].instances[0].forms],
            ["laboratuvar", "hasta_bilgileri"],
        )

    def test_action_only_repeating_event_has_no_phantom_instance(self) -> None:
        action = {
            "kind": "event",
            "event_id": "followup_arm_1",
            "event_label": "İzlem",
            "next_instance": "1",
        }
        nav_model = build_event_nav_model(
            FormRenderModel(project_id="17", record="1", title="1", sections=[]),
            [action],
        )

        self.assertEqual(len(nav_model.groups), 1)
        self.assertEqual(nav_model.groups[0].label, "İzlem")
        self.assertEqual(nav_model.groups[0].instances, [])
        self.assertEqual(nav_model.groups[0].repeat_actions, [action])

    def test_action_only_repeating_form_uses_unnumbered_event_context(self) -> None:
        action = {
            "kind": "form",
            "form_name": "notlar",
            "form_label": "Notlar",
            "event_id": "",
        }
        nav_model = build_event_nav_model(
            FormRenderModel(project_id="17", record="1", title="1", sections=[]),
            [action],
            language="tr",
        )

        self.assertEqual(nav_model.groups[0].label, "Genel formlar")
        self.assertEqual([item.instance for item in nav_model.groups[0].instances], [""])
        self.assertEqual(nav_model.groups[0].instances[0].forms[0].repeat_actions, [action])


class DataEntryEventNavWidgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = get_qapplication()

    def test_event_header_is_unique_collapsible_and_owns_contextual_add(self) -> None:
        widget = DataEntryEventNav(language="tr")
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())
        widget.show()
        self.app.processEvents()

        self.assertEqual(set(widget.group_headers), {"baseline_arm_1", "biopsy_arm_1"})
        self.assertEqual(widget.group_headers["biopsy_arm_1"].text(), "▾  Klasik Biyopsi")
        widget.group_headers["baseline_arm_1"].click()
        self.assertFalse(widget.group_contents["baseline_arm_1"].isVisible())
        self.assertTrue(widget.group_headers["baseline_arm_1"].text().startswith("▸"))

        event_buttons = [
            button for action, button in widget.repeat_buttons if action.get("kind") == "event"
        ]
        self.assertEqual(len(event_buttons), 1)
        self.assertEqual(event_buttons[0].parent().property("event_id"), "biopsy_arm_1")
        self.assertEqual(event_buttons[0].toolTip(), "Yeni Klasik Biyopsi kaydı ekle")
        self.assertNotIn("event", event_buttons[0].toolTip().lower())

    def test_event_instance_chips_filter_forms_without_duplicate_headers(self) -> None:
        widget = DataEntryEventNav(language="tr")
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())
        widget.show()
        self.app.processEvents()

        self.assertEqual(
            set(widget.instance_buttons),
            {("biopsy_arm_1", "1"), ("biopsy_arm_1", "2")},
        )
        self.assertTrue(widget.instance_bodies[("biopsy_arm_1", "1")].isVisible())
        self.assertFalse(widget.instance_bodies[("biopsy_arm_1", "2")].isVisible())

        widget.instance_buttons[("biopsy_arm_1", "2")].click()

        self.assertFalse(widget.instance_bodies[("biopsy_arm_1", "1")].isVisible())
        self.assertTrue(widget.instance_bodies[("biopsy_arm_1", "2")].isVisible())
        self.assertTrue(widget.instance_buttons[("biopsy_arm_1", "2")].property("active"))
        self.assertEqual(widget.selected_instances()["biopsy_arm_1"], "2")

    def test_selecting_form_reopens_group_and_selects_its_event_instance(self) -> None:
        widget = DataEntryEventNav(language="tr")
        selected = []
        widget.targetActivated.connect(selected.append)
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())
        widget.show()
        self.app.processEvents()
        widget.set_group_expanded("biopsy_arm_1", False)
        widget.select_event_instance("biopsy_arm_1", "1")

        widget.target_buttons[5].click()

        self.assertEqual(selected, [5])
        self.assertTrue(widget.group_contents["biopsy_arm_1"].isVisible())
        self.assertEqual(widget.selected_instances()["biopsy_arm_1"], "2")
        self.assertTrue(widget.instance_bodies[("biopsy_arm_1", "2")].isVisible())
        self.assertTrue(widget.target_buttons[5].property("active"))
        self.assertTrue(widget.form_rows[("biopsy_arm_1", "2", "biyopsi")].property("active"))

    def test_repeating_form_instances_and_inline_add_keep_signal_contract(self) -> None:
        widget = DataEntryEventNav(language="tr")
        selected = []
        repeated = []
        widget.targetActivated.connect(selected.append)
        widget.repeatActionRequested.connect(repeated.append)
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())

        self.assertEqual(widget.target_buttons[1].text(), "#1")
        self.assertEqual(widget.target_buttons[2].text(), "#2")
        form_add = next(
            button for action, button in widget.repeat_buttons if action.get("kind") == "form"
        )
        self.assertEqual(form_add.parent().property("form_name"), "laboratuvar")
        self.assertEqual(form_add.toolTip(), "Laboratuvar için yeni tekrar ekle")

        widget.target_buttons[2].click()
        form_add.click()
        self.assertEqual(selected, [2])
        self.assertEqual(repeated, [repeat_actions()[1]])

    def test_action_only_event_renders_plus_without_instance_chip(self) -> None:
        action = {
            "kind": "event",
            "event_id": "followup_arm_1",
            "event_label": "İzlem",
        }
        widget = DataEntryEventNav(language="tr")
        repeated = []
        widget.repeatActionRequested.connect(repeated.append)
        widget.set_record_model(
            FormRenderModel(project_id="17", record="1", title="1", sections=[]),
            repeat_actions=[action],
        )

        self.assertEqual(set(widget.group_headers), {"followup_arm_1"})
        self.assertEqual(widget.instance_buttons, {})
        self.assertEqual(widget.instance_bodies, {})
        self.assertEqual(len(widget.repeat_buttons), 1)
        widget.repeat_buttons[0][1].click()
        self.assertEqual(repeated, [action])

    def test_navigation_state_getters_and_setters_round_trip(self) -> None:
        widget = DataEntryEventNav(language="tr")
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())
        widget.show()
        self.app.processEvents()
        widget.set_expanded_keys(["biopsy_arm_1"])
        widget.set_selected_instances({"biopsy_arm_1": "2"})
        widget.set_scroll_state({"vertical": 12, "horizontal": 0})
        state = widget.navigation_state()

        self.assertEqual(state["expanded_keys"], ["biopsy_arm_1"])
        self.assertEqual(state["selected_instances"]["biopsy_arm_1"], "2")
        self.assertIn("vertical", state["scroll"])

        widget.set_expanded_keys([])
        widget.set_selected_instances({"biopsy_arm_1": "1"})
        widget.restore_navigation_state(state)
        self.app.processEvents()

        self.assertEqual(widget.expanded_keys(), {"biopsy_arm_1"})
        self.assertEqual(widget.selected_instances()["biopsy_arm_1"], "2")
        self.assertTrue(widget.instance_buttons[("biopsy_arm_1", "2")].property("active"))

    def test_accessible_names_explain_event_and_form_instance_actions(self) -> None:
        widget = DataEntryEventNav(language="en")
        widget.set_record_model(record_model(), repeat_actions=repeat_actions())

        self.assertEqual(
            widget.instance_buttons[("biopsy_arm_1", "2")].accessibleName(),
            "Show Klasik Biyopsi record #2",
        )
        self.assertIn("Expand or collapse", widget.group_headers["baseline_arm_1"].accessibleName())
        event_add = next(
            button for action, button in widget.repeat_buttons if action.get("kind") == "event"
        )
        self.assertEqual(event_add.accessibleName(), "Add another Klasik Biyopsi record")


if __name__ == "__main__":
    unittest.main()
