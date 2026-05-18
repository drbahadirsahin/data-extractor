from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import olefile
from pypdf import PdfReader
from pypdf._page import PageObject

from helpers import load_text

TEXT_EXTENSIONS = {".txt"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
DOCX_EXTENSIONS = {".docx"}
DOC_EXTENSIONS = {".doc"}
ODT_EXTENSIONS = {".odt"}
RTF_EXTENSIONS = {".rtf"}

SUPPORTED_EXTENSIONS = (
    TEXT_EXTENSIONS
    | PDF_EXTENSIONS
    | IMAGE_EXTENSIONS
    | DOCX_EXTENSIONS
    | DOC_EXTENSIONS
    | ODT_EXTENSIONS
    | RTF_EXTENSIONS
)

OCR_LANGUAGES = ("tur", "eng")
OCR_PAGE_SEGMENTATION_MODE = "6"
OCR_TIMEOUT_SECONDS = 120
TESSERACT_LANG_TIMEOUT_SECONDS = 10


def get_file_type(file_path: Path) -> str:
    return file_path.suffix.lower()


def is_text_file(file_path: Path) -> bool:
    return get_file_type(file_path) in TEXT_EXTENSIONS


def is_pdf_file(file_path: Path) -> bool:
    return get_file_type(file_path) in PDF_EXTENSIONS


def is_image_file(file_path: Path) -> bool:
    return get_file_type(file_path) in IMAGE_EXTENSIONS


def is_docx_file(file_path: Path) -> bool:
    return get_file_type(file_path) in DOCX_EXTENSIONS


def is_doc_file(file_path: Path) -> bool:
    return get_file_type(file_path) in DOC_EXTENSIONS


def is_odt_file(file_path: Path) -> bool:
    return get_file_type(file_path) in ODT_EXTENSIONS


def is_rtf_file(file_path: Path) -> bool:
    return get_file_type(file_path) in RTF_EXTENSIONS


def is_supported_file(file_path: Path) -> bool:
    return get_file_type(file_path) in SUPPORTED_EXTENSIONS


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [line.strip() for line in text.split("\n")]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def load_file(file_path: str | Path) -> str:
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not is_supported_file(file_path):
        raise ValueError(f"Unsupported file type: {file_path}")

    if is_text_file(file_path):
        text = load_text(file_path)
    elif is_pdf_file(file_path):
        text = extract_pdf_text(file_path)
    elif is_image_file(file_path):
        text = extract_image_text(file_path)
    elif is_docx_file(file_path):
        text = extract_docx_text(file_path)
    elif is_doc_file(file_path):
        text = extract_doc_text(file_path)
    elif is_odt_file(file_path):
        text = extract_odt_text(file_path)
    elif is_rtf_file(file_path):
        text = extract_rtf_text(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")

    normalized = normalize_text(text)
    if not normalized:
        raise ValueError(f"No extractable text found in file: {file_path}")
    return normalized


def extract_pdf_text(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    pages: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
            continue
        ocr_text = extract_pdf_page_ocr_text(page)
        if ocr_text.strip():
            pages.append(ocr_text)
    text = "\n\n".join(pages)
    if text.strip():
        return text
    raise ValueError(
        f"PDF contains no extractable text: {file_path}. "
        "No selectable text or OCR-eligible page images were found."
    )


def extract_image_text(file_path: Path) -> str:
    tesseract_path = find_command("tesseract")
    if not tesseract_path:
        raise ValueError(
            f"Tesseract is not available for OCR: {file_path}. "
            "Image files require a local OCR engine."
        )
    return run_tesseract_ocr(file_path, tesseract_path)


def extract_docx_text(file_path: Path) -> str:
    xml_parts = extract_xml_parts(
        file_path,
        primary_members=["word/document.xml"],
        extra_prefixes=["word/header", "word/footer"],
    )
    return "\n\n".join(part for part in xml_parts if part.strip())


def extract_odt_text(file_path: Path) -> str:
    xml_parts = extract_xml_parts(file_path, primary_members=["content.xml"])
    return "\n\n".join(part for part in xml_parts if part.strip())


def extract_rtf_text(file_path: Path) -> str:
    raw = file_path.read_text(encoding="latin-1", errors="ignore")
    text = decode_rtf(raw)
    if text.strip():
        return text
    raise ValueError(f"No extractable RTF text found in file: {file_path}")


def extract_doc_text(file_path: Path) -> str:
    extractors = [
        extract_doc_with_textutil,
        extract_doc_with_antiword,
        extract_doc_with_soffice,
        extract_doc_with_ole_strings,
        extract_doc_with_plain_strings,
    ]
    last_error: Exception | None = None
    for extractor in extractors:
        try:
            text = extractor(file_path)
        except Exception as exc:
            last_error = exc
            continue
        if text.strip():
            return text
    raise ValueError(
        f"Unable to extract legacy .doc content from {file_path}. "
        f"Last error: {last_error}"
    )


def extract_xml_parts(
    file_path: Path,
    primary_members: list[str],
    extra_prefixes: list[str] | None = None,
) -> list[str]:
    extra_prefixes = extra_prefixes or []
    texts: list[str] = []
    with zipfile.ZipFile(file_path) as archive:
        members = set(archive.namelist())
        selected_members: list[str] = [member for member in primary_members if member in members]
        for member in sorted(members):
            if any(member.startswith(prefix) and member.endswith(".xml") for prefix in extra_prefixes):
                selected_members.append(member)
        if not selected_members:
            raise ValueError(f"Expected XML payload not found in file: {file_path}")
        for member in selected_members:
            xml_text = archive.read(member).decode("utf-8", errors="ignore")
            texts.append(extract_text_from_xml(xml_text))
    return texts


def extract_text_from_xml(xml_text: str) -> str:
    root = ET.fromstring(xml_text)
    parts: list[str] = []
    for element in root.iter():
        tag = local_name(element.tag)
        if tag in {"tab"}:
            parts.append("\t")
        if element.text:
            parts.append(element.text)
        if tag in {"p", "br", "line-break", "h"}:
            parts.append("\n")
        if element.tail:
            parts.append(element.tail)
    return "".join(parts)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def decode_rtf(raw: str) -> str:
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"\\par[d]?|\\line", "\n", raw)

    def unicode_replacer(match: re.Match[str]) -> str:
        value = int(match.group(1))
        if value < 0:
            value += 65536
        return chr(value)

    raw = re.sub(r"\\u(-?\d+)\??", unicode_replacer, raw)
    raw = re.sub(
        r"\\'([0-9a-fA-F]{2})",
        lambda match: bytes.fromhex(match.group(1)).decode("cp1254", errors="ignore"),
        raw,
    )
    raw = re.sub(r"\\[a-zA-Z]+\d* ?", "", raw)
    raw = raw.replace("{", "").replace("}", "").replace("\\", "")
    return raw


def extract_doc_with_textutil(file_path: Path) -> str:
    textutil_path = find_command("textutil")
    if not textutil_path:
        raise RuntimeError("textutil is not available")
    completed = subprocess.run(
        [textutil_path, "-convert", "txt", "-stdout", str(file_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def extract_doc_with_antiword(file_path: Path) -> str:
    antiword_path = find_command("antiword")
    if not antiword_path:
        raise RuntimeError("antiword is not available")
    completed = subprocess.run(
        [antiword_path, str(file_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def extract_doc_with_soffice(file_path: Path) -> str:
    soffice_path = find_command("soffice") or find_command("libreoffice")
    if not soffice_path:
        raise RuntimeError("LibreOffice is not available")
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            [soffice_path, "--headless", "--convert-to", "txt:Text", "--outdir", temp_dir, str(file_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        output_path = Path(temp_dir) / f"{file_path.stem}.txt"
        if not output_path.exists():
            raise RuntimeError("LibreOffice conversion did not produce a TXT file")
        return load_text(output_path)


def extract_doc_with_ole_strings(file_path: Path) -> str:
    if not olefile.isOleFile(str(file_path)):
        raise RuntimeError("File is not a valid OLE document")
    with olefile.OleFileIO(str(file_path)) as ole:
        if not ole.exists("WordDocument"):
            raise RuntimeError("WordDocument stream not found")
        data = ole.openstream("WordDocument").read()
    return decode_binary_text(data)


def extract_doc_with_plain_strings(file_path: Path) -> str:
    strings_path = find_command("strings")
    if strings_path:
        completed = subprocess.run(
            [strings_path, "-n", "4", str(file_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout
    return decode_binary_text(file_path.read_bytes())


def decode_binary_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-16le", "cp1254", "latin-1"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        if enough_printable_text(text):
            return text
    fallback = data.decode("latin-1", errors="ignore")
    if enough_printable_text(fallback):
        return fallback
    printable_chunks = re.findall(rb"[\x20-\x7E\xA0-\xFF]{4,}", data)
    return "\n".join(chunk.decode("latin-1", errors="ignore") for chunk in printable_chunks)


def enough_printable_text(text: str) -> bool:
    cleaned = text.replace("\x00", "").strip()
    if len(cleaned) < 20:
        return False
    printable = sum(1 for char in cleaned if char.isprintable() or char in "\n\t")
    return printable / max(len(cleaned), 1) > 0.8


def find_command(command: str) -> str | None:
    return shutil.which(str(command))


def extract_pdf_page_ocr_text(page: PageObject) -> str:
    tesseract_path = find_command("tesseract")
    if not tesseract_path:
        return ""

    image_texts: list[str] = []
    for image in sort_page_images_for_ocr(page):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as temp_file:
            image.image.save(temp_file.name, format="PNG")
            try:
                text = run_tesseract_ocr(Path(temp_file.name), tesseract_path)
            except ValueError:
                continue
        normalized = normalize_text(text)
        if normalized and normalized not in image_texts:
            image_texts.append(normalized)

    return "\n\n".join(image_texts)


def sort_page_images_for_ocr(page: PageObject) -> list:
    images = list(page.images)
    return sorted(
        images,
        key=lambda image: image.image.size[0] * image.image.size[1],
        reverse=True,
    )


def run_tesseract_ocr(image_path: Path, tesseract_path: str) -> str:
    languages = get_available_tesseract_languages(tesseract_path)
    if not languages:
        raise ValueError(
            "Tesseract is installed, but no supported OCR language pack is available. "
            "Install at least 'eng' or 'tur'."
        )
    try:
        completed = subprocess.run(
            [
                tesseract_path,
                str(image_path),
                "stdout",
                "-l",
                languages,
                "--psm",
                OCR_PAGE_SEGMENTATION_MODE,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise ValueError(f"OCR failed for image file {image_path}: {message}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(
            f"OCR timed out after {OCR_TIMEOUT_SECONDS} seconds for image file {image_path}."
        ) from exc
    return completed.stdout


def get_available_tesseract_languages(tesseract_path: str) -> str:
    try:
        completed = subprocess.run(
            [tesseract_path, "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
            timeout=TESSERACT_LANG_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    available = {
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.startswith("List of available languages")
    }
    selected = [language for language in OCR_LANGUAGES if language in available]
    return "+".join(selected)
