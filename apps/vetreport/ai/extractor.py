"""
vetreport.ai.extractor
~~~~~~~~~~~~~~~~~~~~~~

Text extraction utilities for uploaded vet report files.

extract_text_from_file(file_obj, content_type) → str
    Dispatches to the correct extractor based on MIME type.
    Returns extracted text or raises ``ExtractionError``.

extract_text_from_pdf(file_obj) → str
    Uses PyPDF2 to extract all page text from an in-memory PDF file.

extract_text_from_txt(file_obj) → str
    Decodes a plain-text file, trying UTF-8 first then Latin-1 as fallback.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MIME_PDF  = "application/pdf"
MIME_TEXT = "text/plain"

ALLOWED_MIME_TYPES = {MIME_PDF, MIME_TEXT}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class ExtractionError(Exception):
    """Raised when text cannot be extracted from the uploaded file."""


def extract_text_from_file(file_obj, content_type: str) -> str:
    """
    Extract plain text from *file_obj* based on its *content_type*.

    Parameters
    ----------
    file_obj     : Django InMemoryUploadedFile or TemporaryUploadedFile
    content_type : str — MIME type declared by the client

    Returns
    -------
    str — extracted text (may be empty if the file contains no selectable text)

    Raises
    ------
    ExtractionError  — unsupported MIME type or extraction failure
    """
    ct = (content_type or "").lower().split(";")[0].strip()

    if ct == MIME_PDF:
        return extract_text_from_pdf(file_obj)
    elif ct == MIME_TEXT:
        return extract_text_from_txt(file_obj)
    else:
        raise ExtractionError(
            f"Unsupported file type '{ct}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}."
        )


def extract_text_from_pdf(file_obj) -> str:
    """
    Extract all selectable text from a PDF file object using PyPDF2.

    Parameters
    ----------
    file_obj : file-like object positioned at the start of the PDF data.

    Returns
    -------
    str — concatenated text from all pages, separated by newlines.

    Raises
    ------
    ExtractionError — if PyPDF2 cannot parse the file.
    """
    try:
        import PyPDF2  # noqa: PLC0415 — deferred to avoid startup cost

        file_obj.seek(0)
        reader = PyPDF2.PdfReader(file_obj)

        pages_text: list[str] = []
        for page_num, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
                pages_text.append(text)
            except Exception as page_exc:
                logger.warning(
                    "extract_text_from_pdf: failed to extract page %d: %s",
                    page_num, page_exc,
                )

        extracted = "\n".join(pages_text).strip()
        logger.debug(
            "extract_text_from_pdf: extracted %d chars from %d pages",
            len(extracted), len(reader.pages),
        )
        return extracted

    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"PDF extraction failed: {exc}") from exc


def extract_text_from_txt(file_obj) -> str:
    """
    Decode a plain-text file, attempting UTF-8 first and Latin-1 as fallback.

    Parameters
    ----------
    file_obj : file-like object

    Returns
    -------
    str — decoded file content.

    Raises
    ------
    ExtractionError — if neither encoding succeeds.
    """
    file_obj.seek(0)
    raw_bytes = file_obj.read()

    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            text = raw_bytes.decode(encoding)
            logger.debug(
                "extract_text_from_txt: decoded %d bytes using %s",
                len(raw_bytes), encoding,
            )
            return text.strip()
        except (UnicodeDecodeError, LookupError):
            continue

    raise ExtractionError(
        "Could not decode the text file. "
        "Please ensure the file is saved in UTF-8 or Latin-1 encoding."
    )
