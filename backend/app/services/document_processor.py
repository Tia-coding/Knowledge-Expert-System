import hashlib
import logging
from pydoc import text
import re
import pytesseract

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


# =========================================================
# DATA CLASSES
# =========================================================

@dataclass
class ExtractedChunk:
    text: str
    metadata: dict[str, Any]


@dataclass
class ExtractionResult:
    text: str
    chunks: list[ExtractedChunk]
    page_count: int
    table_count: int


# =========================================================
# FILE HASH
# =========================================================

def sha256_file(path: Path) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as file:

        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text: str) -> str:

    if not text:
        return ""

    text = text.replace("\x00", " ")

    # Repair common PDF ligature extraction losses before filtering.
    ligature_repairs = {
        r"\brst\b": "first",
        r"\bde\s+ned\b": "defined",
        r"\bde\s+ning\b": "defining",
        r"\becient\b": "efficient",
        r"\beciency\b": "efficiency",
        r"\bdierent\b": "different",
        r"\bdierence\b": "difference",
        r"\bspecied\b": "specified",
        r"\bbriey\b": "briefly",
    }

    for pattern, repaired in ligature_repairs.items():
        text = re.sub(pattern, repaired, text)

    # Fix OCR hyphen line breaks
    text = re.sub(
        r"(\w)-\n(\w)",
        r"\1\2",
        text,
    )

    # Normalize spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    # Normalize line breaks
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    # Remove OCR artifacts
    text = re.sub(
        r"[|]{3,}",
        " ",
        text,
    )

    # Remove weird symbol noise
    text = re.sub(
        r"[^\w\s.,:;!?()\-\n/#%+*=<>]{6,}",
        " ",
        text,
    )

    # Remove repeated chars
    text = re.sub(
        r"(.)\1{7,}",
        r"\1",
        text,
    )

    # Preserve important technical short words
    allowed_short_words = {
        "a",
        "an",
        "of",
        "to",
        "is",
        "in",
        "on",
        "or",
        "AI",
        "ML",
        "DL",
        "DB",
        "OS",
        "IP",
        "UI",
        "UX",
        "API",
        "SQL",
        "C",
        "C++",
    }

    def preserve_word(match):

        word = match.group(0)

        return (
            word
            if word in allowed_short_words
            else ""
        )

    text = re.sub(
        r"\b[a-zA-Z]{1,2}\b",
        preserve_word,
        text,
    )

    text = re.sub(
        r"[ \t]*\n[ \t]*",
        "\n",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# =========================================================
# TEXT QUALITY FILTER
# =========================================================

def is_meaningful_text(text: str) -> bool:

    if not text:
        return False

    text = text.strip()

    if len(text) < 120:
        return False

    special_ratio = (
        len(
            re.findall(
                r"[^a-zA-Z0-9\s.,:;()\-]",
                text,
            )
        )
        / max(len(text), 1)
    )

    if special_ratio > 0.20:
        return False

    words = re.findall(
        r"\b[a-zA-Z]{3,}\b",
        text,
    )

    if len(words) < 12:
        return False

    garbage_patterns = [
        r"[_]{2,}",
        r"[^\s]{35,}",
    ]

    for pattern in garbage_patterns:

        if re.search(pattern, text):
            return False

    return True


# =========================================================
# CODE DETECTION
# =========================================================

def looks_like_code(line: str) -> bool:

    return bool(
        re.search(
            r"\b(def|class|import|for|while|if|else|return|SELECT|FROM|public|void|function|int|float|printf|cout)\b|[{};=<>]",
            line,
        )
    )


# =========================================================
# PRESERVE CODE BLOCKS
# =========================================================

def preserve_code_blocks(text: str) -> str:

    lines = text.splitlines()

    output = []

    in_code = False

    for line in lines:

        code_line = looks_like_code(line)

        if code_line and not in_code:

            output.append("```")

            in_code = True

        if (
            not code_line
            and in_code
            and line.strip()
        ):

            output.append("```")

            in_code = False

        output.append(line)

    if in_code:

        output.append("```")

    return "\n".join(output)


# =========================================================
# DOCX EXTRACTION
# =========================================================

def extract_docx(
    path: Path,
) -> tuple[list[tuple[int, str]], int]:

    from docx import (
        Document as DocxDocument,
    )

    doc = DocxDocument(path)

    parts = []

    table_count = 0

    for paragraph in doc.paragraphs:

        text = paragraph.text.strip()

        if text:

            parts.append(text)

    for table in doc.tables:

        table_count += 1

        rows = []

        for row in table.rows:

            cells = [
                cell.text.strip().replace(
                    "\n",
                    " ",
                )
                for cell in row.cells
            ]

            rows.append(
                " | ".join(cells)
            )

        parts.append(
            "\n[TABLE]\n"
            + "\n".join(rows)
        )

    return [
        (
            1,
            "\n\n".join(parts),
        )
    ], table_count


# =========================================================
# IMAGE OCR EXTRACTION
# =========================================================

def extract_images_from_pdf_page(
    page,
) -> str:

    extracted_text = []

    try:

        images = page.images

        if not images:

            return ""

        for _ in images:

            try:

                image = page.to_image(
                    resolution=250
                ).original

                text = (
                    pytesseract.image_to_string(
                        image
                    )
                )

                text = clean_text(text)

                if (
                    is_meaningful_text(text)
                ):

                    extracted_text.append(
                        text
                    )

            except Exception:
                continue

    except Exception:

        return ""

    return "\n".join(extracted_text)


# =========================================================
# PDF EXTRACTION
# =========================================================

def extract_pdf_text(
    path: Path,
) -> tuple[list[tuple[int, str]], int]:

    pages = []

    table_count = 0

    try:
        import fitz
    except ImportError:
        fitz = None

    if fitz is not None:

        try:

            pdf = fitz.open(path)

            for page_num, page in enumerate(
                pdf,
                start=1,
            ):

                text = (
                    page.get_text("text")
                    or ""
                )

                text = clean_text(text)

                # OCR support for image-heavy PDFs
                if not is_meaningful_text(text):

                    try:

                        pix = page.get_pixmap(
                            dpi=300
                        )

                        import PIL.Image
                        import io

                        image = PIL.Image.open(
                            io.BytesIO(
                                pix.tobytes("png")
                            )
                        )

                        ocr_text = (
                            pytesseract.image_to_string(
                                image
                            )
                        )

                        ocr_text = clean_text(
                            ocr_text
                        )

                        if (
                            is_meaningful_text(
                                ocr_text
                            )
                        ):

                            text = ocr_text

                    except Exception:
                        pass

                pages.append(
                    (
                        page_num,
                        text,
                    )
                )

            pdf.close()

        except Exception:

            logger.exception(
                "PyMuPDF extraction failed for %s; trying pdfplumber/PyPDF2 fallback.",
                path,
            )

    if pages:
        return pages, table_count

    try:

        import pdfplumber

        with pdfplumber.open(path) as pdf:

            for page_num, page in enumerate(
                pdf.pages,
                start=1,
            ):

                text = clean_text(
                    page.extract_text() or ""
                )

                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []

                table_lines = []
                for table in tables:
                    table_count += 1
                    for row in table:
                        cells = [
                            clean_text(cell or "")
                            for cell in row
                        ]
                        table_lines.append(
                            " | ".join(cells)
                        )

                if table_lines:
                    text = (
                        text
                        + "\n\n[TABLE]\n"
                        + "\n".join(table_lines)
                    ).strip()

                pages.append(
                    (
                        page_num,
                        text,
                    )
                )

    except Exception:

        logger.exception(
            "pdfplumber extraction failed for %s; trying PyPDF2 fallback.",
            path,
        )

    if pages:
        return pages, table_count

    try:

        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))

        for page_num, page in enumerate(
            reader.pages,
            start=1,
        ):
            pages.append(
                (
                    page_num,
                    clean_text(page.extract_text() or ""),
                )
            )

    except Exception:

        logger.exception(
            "PyPDF2 extraction failed for %s",
            path,
        )

    return pages, table_count


# =========================================================
# OCR FOR SCANNED PDFs
# =========================================================

def extract_pdf_ocr(
    path: Path,
    existing_pages: list[
        tuple[int, str]
    ],
) -> list[tuple[int, str]]:

    try:

        from pdf2image import (
            convert_from_path,
        )

    except Exception:

        logger.warning(
            "OCR libraries unavailable for %s",
            path,
        )

        return existing_pages

    page_map = {
        page: text
        for page, text in existing_pages
    }

    try:

        images = convert_from_path(
            str(path),
            dpi=180, 
            thread_count=2,
        )

        for idx, image in enumerate(
            images,
            start=1,
        ):

            existing = (
                page_map.get(idx, "")
                or ""
            )

            meaningful_existing = (
                is_meaningful_text(
                    existing
                )
            )

            if meaningful_existing:
                continue

            ocr_text = (
                pytesseract.image_to_string(
                    image
                )
                or ""
            )

            ocr_text = clean_text(
                ocr_text
            )

            if (
                not is_meaningful_text(
                    ocr_text
                )
            ):
                continue

            if (
                len(ocr_text)
                > len(existing) * 1.5
            ):

                page_map[idx] = ocr_text

    except Exception:

        logger.exception(
            "OCR failed for %s",
            path,
        )

    return sorted(
        page_map.items(),
        key=lambda item: item[0],
    )


# =========================================================
# TXT EXTRACTION
# =========================================================

def extract_txt(
    path: Path,
) -> tuple[list[tuple[int, str]], int]:

    return [
        (
            1,
            path.read_text(
                encoding="utf-8",
                errors="ignore",
            ),
        )
    ], 0


# =========================================================
# REMOVE DUPLICATE CHUNKS
# =========================================================

def deduplicate_chunks(
    chunks: list[ExtractedChunk],
) -> list[ExtractedChunk]:

    unique = []

    seen = set()

    for chunk in chunks:

        key = (
            chunk.text[:500]
            .strip()
            .lower()
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(chunk)

    return unique


def classify_chunk_kind(text: str) -> str:
    """Lightweight retrieval hint stored with metadata for future ingests."""

    lowered = text.lower()

    if re.search(
        r"\b(difference between|compare|comparison|versus|whereas)\b",
        lowered,
    ):
        return "comparison"

    if re.search(
        r"\b(types of|kinds of|classified into|classification of)\b",
        lowered,
    ):
        return "type_list"

    if re.search(
        r"\b(refers to|defined as|is a|is an|is the)\b",
        lowered,
    ):
        return "definition"

    return "general"


# =========================================================
# MAIN DOCUMENT EXTRACTION
# =========================================================

def extract_document(
    path: Path,
    filename: str,
    document_type: str,
) -> ExtractionResult:

    suffix = path.suffix.lower()

    if suffix == ".pdf":

        pages, table_count = (
            extract_pdf_text(path)
        )

        pages = extract_pdf_ocr(
            path,
            pages,
        )

    elif suffix == ".docx":

        pages, table_count = (
            extract_docx(path)
        )

    elif suffix in {
        ".txt",
        ".md",
        ".csv",
    }:

        pages, table_count = (
            extract_txt(path)
        )

    else:

        raise ValueError(
            "Unsupported document type"
        )

    splitter = (
        RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            separators=[
                "\n# ",
                "\n## ",
                "\n### ",
                "\n[TABLE]",
                "\n[IMAGE_TEXT]",
                "\n```",
                "\n\n",
                "\n",
                ". ",
                "! ",
                "? ",
                "; ",
                ", ",
                " ",
                "",
            ],
            keep_separator=True,
        )
    )

    chunks = []

    all_text = []

    for page, raw in pages:

        text = preserve_code_blocks(
            clean_text(raw)
        )

        text = clean_text(text)

        if not text:
            continue

        all_text.append(
            f"[Page {page}]\n{text}"
        )

        sections = re.split(
            r"\n(?=[A-Z][A-Za-z0-9 ]{2,50}\n)",
            text
        )

        if len(sections) > 1:
            split_chunks = []

            for section in sections:
                split_chunks.extend(
                    splitter.split_text(section)
                )
        else:
            split_chunks = splitter.split_text(text)

        for idx, chunk in enumerate(
            split_chunks,
            start=1,
        ):

            cleaned = clean_text(
                chunk
            )

            if (
                len(cleaned.strip())
                < 80
            ):
                continue

            if (
                not is_meaningful_text(
                    cleaned
                )
                and "[TABLE]"
                not in cleaned
                and "[IMAGE_TEXT]"
                not in cleaned
            ):
                continue

            chunks.append(
                ExtractedChunk(
                    text=cleaned,
                    metadata={
                        "file": filename,
                        "filename": filename,
                        "page": page,
                        "chunk_id": (
                            f"{path.stem}"
                            f"-p{page}"
                            f"-c{idx}"
                        ),
                        "document_type": (
                            document_type
                        ),
                        "chunk_kind": classify_chunk_kind(
                            cleaned
                        ),
                    },
                )
            )

    chunks = deduplicate_chunks(
        chunks
    )

    if not chunks:

        raise ValueError(
            "No searchable text extracted"
        )

    logger.info(
        f"Extracted {len(chunks)} chunks "
        f"from {filename}"
    )

    return ExtractionResult(
        text="\n\n".join(all_text),
        chunks=chunks,
        page_count=max(
            len(pages),
            1,
        ),
        table_count=table_count,
    )
