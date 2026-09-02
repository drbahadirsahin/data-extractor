from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea

from data_entry_form_model import (
    CHECKBOX_EDITOR,
    DATE_EDITOR,
    DROPDOWN_EDITOR,
    FormChoiceModel,
    FormFieldModel,
    FormRenderModel,
    FormSectionModel,
    RADIO_EDITOR,
    READONLY_EDITOR,
    TEXT_AREA_EDITOR,
    TEXT_EDITOR,
)
from gui.clinical_main_window import ClinicalMainWindow
from gui.clinical_styles import CLINICAL_STYLE
from scripts.render_clinical_ui import build_preview_runtime


def sample_form_model() -> FormRenderModel:
    baseline = "baseline_arm_1"
    followup = "followup_arm_1"
    return FormRenderModel(
        project_id="101",
        record="D-003",
        title="Kayıt D-003 · Örnek Hasta",
        sections=[
            FormSectionModel(
                form_name="hasta_bilgileri",
                title="Hasta Bilgileri",
                event_id=baseline,
                event_label="Tıbbi Bilgiler ve Tanı",
                completion_status="1",
                completion_present=True,
                fields=[
                    FormFieldModel(
                        "record_id",
                        "hasta_bilgileri",
                        "Kayıt numarası",
                        READONLY_EDITOR,
                        value="D-003",
                        read_only=True,
                        section_header="Kimlik ve demografi",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "dogum_tarihi",
                        "hasta_bilgileri",
                        "Doğum tarihi",
                        DATE_EDITOR,
                        value="1975-04-12",
                        validation="date_ymd",
                        required=True,
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "ad",
                        "hasta_bilgileri",
                        "Ad",
                        TEXT_EDITOR,
                        value="Deniz",
                        required=True,
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "soyad",
                        "hasta_bilgileri",
                        "Soyad",
                        TEXT_EDITOR,
                        value="Örnek",
                        required=True,
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "cinsiyet",
                        "hasta_bilgileri",
                        "Cinsiyet",
                        DROPDOWN_EDITOR,
                        value="1",
                        choices=[FormChoiceModel("1", "Erkek"), FormChoiceModel("2", "Kadın")],
                        required=True,
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "telefon",
                        "hasta_bilgileri",
                        "Telefon",
                        TEXT_EDITOR,
                        value="0505 123 45 67",
                        section_header="İletişim bilgileri",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "eposta",
                        "hasta_bilgileri",
                        "E-posta",
                        TEXT_EDITOR,
                        value="ornek@example.com",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "boy",
                        "hasta_bilgileri",
                        "Boy (cm)",
                        TEXT_EDITOR,
                        value="175",
                        validation="integer",
                        section_header="Fiziksel bilgiler",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "kilo",
                        "hasta_bilgileri",
                        "Kilo (kg)",
                        TEXT_EDITOR,
                        value="78.4",
                        validation="number_1dp",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "vki",
                        "hasta_bilgileri",
                        "VKİ (kg/m²)",
                        READONLY_EDITOR,
                        value="25.60",
                        field_type="calc",
                        calc_expression="[kilo] / (([boy] / 100) * ([boy] / 100))",
                        read_only=True,
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "ek_risk_var",
                        "hasta_bilgileri",
                        "Ek risk faktörü var mı?",
                        RADIO_EDITOR,
                        value="1",
                        choices=[FormChoiceModel("1", "Evet"), FormChoiceModel("0", "Hayır")],
                        section_header="Klinik notlar",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "riskler",
                        "hasta_bilgileri",
                        "Risk faktörleri",
                        CHECKBOX_EDITOR,
                        value=["1", "3"],
                        choices=[
                            FormChoiceModel("1", "Hipertansiyon"),
                            FormChoiceModel("2", "Diyabet"),
                            FormChoiceModel("3", "Aile öyküsü"),
                        ],
                        branching_logic="[ek_risk_var] = '1'",
                        event_id=baseline,
                    ),
                    FormFieldModel(
                        "klinik_not",
                        "hasta_bilgileri",
                        "Kısa klinik not",
                        TEXT_AREA_EDITOR,
                        value="Kontrol muayenesi planlandı.",
                        note="Gerekli olduğunda kısa ve nesnel bir açıklama girin.",
                        event_id=baseline,
                    ),
                ],
            ),
            FormSectionModel(
                form_name="tibbi_bilgiler",
                title="Tıbbi Bilgiler",
                event_id=baseline,
                event_label="Tıbbi Bilgiler ve Tanı",
                fields=[],
            ),
            FormSectionModel(
                form_name="izlem",
                title="Tedavi Sonrası İzlem",
                event_id=followup,
                event_label="İzlem",
                instance="1",
                fields=[],
            ),
        ],
    )


def render(
    output: Path,
    width: int,
    height: int,
    *,
    open_calendar: bool = False,
    focus_field: str | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(CLINICAL_STYLE)
    with tempfile.TemporaryDirectory(prefix="llm-extractor-form-ui-") as temp_dir:
        runtime = build_preview_runtime(Path(temp_dir))
        window = ClinicalMainWindow(runtime)
        target = window._window
        target.resize(width, height)
        window.set_page("data_entry")
        page = window.data_entry_page
        for record_label in (
            "D-001 · Örnek Kayıt",
            "D-002 · Örnek Kayıt",
            "D-003 · Örnek Kayıt",
            "D-004 · Örnek Kayıt",
            "D-005 · Örnek Kayıt",
        ):
            page.record_list.addItem(record_label)
        page.record_list.setCurrentRow(2)
        page.current_model = sample_form_model()
        page.form_widget.set_model(
            page.current_model,
            event_order=["baseline_arm_1", "followup_arm_1"],
            form_order=["hasta_bilgileri", "tibbi_bilgiler", "izlem"],
        )
        page.set_form_actions_enabled(True)
        page.set_activity("Kayıt hazır", "Form alanları düzenlenebilir.", tone="success")
        target.show()
        app.processEvents()
        if focus_field:
            row = page.form_widget.field_rows.get(focus_field)
            current_page = page.form_widget.form_stack.currentWidget() if page.form_widget.form_stack is not None else None
            scroll = current_page.findChild(QScrollArea, "DataEntrySectionScroll") if current_page is not None else None
            if row is not None and scroll is not None:
                scroll.ensureWidgetVisible(row, 20, 20)
                app.processEvents()
        if open_calendar:
            date_editor = page.form_widget.editor_widgets.get("dogum_tarihi")
            if date_editor is not None:
                date_editor._data_entry_date_menu.popup(
                    date_editor._data_entry_date_line_edit.mapToGlobal(
                        date_editor._data_entry_date_line_edit.rect().bottomLeft()
                    )
                )
                app.processEvents()
        target.repaint()
        app.processEvents()
        image = QPixmap(target.size())
        image.fill(Qt.GlobalColor.transparent)
        target.render(image)
        if not image.save(str(output)):
            raise RuntimeError(f"Could not save preview: {output}")
        target.close()
        target.deleteLater()
        app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a PHI-free data-entry form preview.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--open-calendar", action="store_true")
    parser.add_argument("--focus-field")
    args = parser.parse_args()
    render(
        args.output.resolve(),
        args.width,
        args.height,
        open_calendar=args.open_calendar,
        focus_field=args.focus_field,
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
