import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from document_parser import load_file


class DocumentParserTests(unittest.TestCase):
    def test_load_text_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.txt"
            path.write_text("Hasta adi: Ali Veli\nPSA: 4.2", encoding="utf-8")
            self.assertEqual(load_file(path), "Hasta adi: Ali Veli\nPSA: 4.2")

    def test_load_docx_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.docx"
            self._write_zip_xml(
                path,
                {
                    "word/document.xml": (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                        "<w:body>"
                        "<w:p><w:r><w:t>Hasta adi: Ayse Kaya</w:t></w:r></w:p>"
                        "<w:p><w:r><w:t>PSA: 7.8</w:t></w:r></w:p>"
                        "</w:body>"
                        "</w:document>"
                    )
                },
            )
            self.assertEqual(load_file(path), "Hasta adi: Ayse Kaya\nPSA: 7.8")

    def test_load_odt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.odt"
            self._write_zip_xml(
                path,
                {
                    "content.xml": (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
                        "<office:body><office:text>"
                        "<text:p>Dogum tarihi: 1970-05-10</text:p>"
                        "<text:p>Sehir: Ankara</text:p>"
                        "</office:text></office:body>"
                        "</office:document-content>"
                    )
                },
            )
            self.assertEqual(load_file(path), "Dogum tarihi: 1970-05-10\nSehir: Ankara")

    def test_load_rtf_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.rtf"
            path.write_text(r"{\rtf1\ansi Hasta adi: Mehmet\par Kreatinin: 1.1}", encoding="latin-1")
            self.assertEqual(load_file(path), "Hasta adi: Mehmet\nKreatinin: 1.1")

    @unittest.skipUnless(shutil.which("tesseract"), "tesseract is required for PDF OCR test")
    def test_load_scanned_pdf_with_ocr(self) -> None:
        font_path = self._find_font_path()
        if not font_path:
            self.skipTest("No truetype font available for stable OCR fixture generation")

        with tempfile.TemporaryDirectory() as temp_dir:
            image = Image.new("RGB", (1600, 400), "white")
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype(font_path, 120)
            draw.text((80, 120), "PSA 4.2", fill="black", font=font)

            path = Path(temp_dir) / "scan.pdf"
            image.save(path, "PDF")

            extracted = load_file(path)
            self.assertIn("PSA 4.2", extracted)

    @staticmethod
    def _write_zip_xml(path: Path, members: dict[str, str]) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            for member_name, content in members.items():
                archive.writestr(member_name, content)

    @staticmethod
    def _find_font_path() -> str | None:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
        return None


if __name__ == "__main__":
    unittest.main()
