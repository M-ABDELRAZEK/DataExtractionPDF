"""Fast PDF text extraction for large PTS documents.

PyMuPDF is used as the primary engine because repeated pdfplumber page parsing is
far too slow for multi-thousand-page specifications. pdfplumber remains an
optional fallback for individual pages that PyMuPDF cannot decode.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator, Tuple, Optional

import pymupdf  # PyMuPDF

try:
    import pdfplumber
except Exception:  # pragma: no cover - fallback is optional
    pdfplumber = None

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Extract PDF pages once using physical page numbers (1..N)."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.total_pages = 0
        self._validate_file()

    def _validate_file(self):
        if not self.file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.file_path}")
        if not self.file_path.is_file():
            raise ValueError(f"Path is not a file: {self.file_path}")
        if self.file_path.suffix.lower() != ".pdf":
            raise ValueError(f"File is not a PDF: {self.file_path}")

        try:
            with pymupdf.open(self.file_path) as doc:
                self.total_pages = doc.page_count
                if self.total_pages <= 0:
                    raise ValueError("PDF contains no pages")
        except Exception as exc:
            raise ValueError(f"Invalid or corrupted PDF file: {exc}") from exc

        logger.info("PDF initialized: %s (%d pages)", self.file_path.name, self.total_pages)

    def extract_text_pages(
        self,
        start_page: int = 0,
        end_page: Optional[int] = None,
        extract_tables: bool = False,
    ) -> Generator[Tuple[int, str, Optional[list]], None, None]:
        """Yield ``(physical_page_number, text, tables)``.

        ``start_page`` is zero-based and ``end_page`` is exclusive. The yielded
        page number is always the physical PDF viewer page number (1-based).

        Table extraction is intentionally not part of the production SLD flow;
        the argument is retained only for backward API compatibility.
        """
        if end_page is None:
            end_page = self.total_pages
        else:
            end_page = min(end_page, self.total_pages)

        if start_page < 0 or start_page >= self.total_pages:
            raise ValueError(f"Start page {start_page} out of range (0-{self.total_pages - 1})")
        if end_page <= start_page:
            raise ValueError(f"End page {end_page} must be greater than start page {start_page}")

        logger.info("Extracting physical PDF pages %d to %d", start_page + 1, end_page)

        with pymupdf.open(self.file_path) as doc:
            for page_index in range(start_page, end_page):
                text = ""
                try:
                    # 'text' preserves a useful reading order while remaining fast.
                    text = doc.load_page(page_index).get_text("text", sort=True) or ""
                except Exception as exc:
                    logger.warning("PyMuPDF failed on page %d: %s", page_index + 1, exc)
                    text = self._fallback_page_text(page_index + 1)

                # Tables are not needed by the fixed-template extractor. Keep a
                # predictable return shape for existing callers.
                tables = [] if extract_tables else None
                yield page_index + 1, text.strip(), tables

                if (page_index + 1) % 250 == 0:
                    logger.debug("Processed %d pages", page_index + 1)

    def _fallback_page_text(self, physical_page_number: int) -> str:
        if pdfplumber is None:
            return ""
        try:
            with pdfplumber.open(self.file_path) as pdf:
                page = pdf.pages[physical_page_number - 1]
                return (page.extract_text(x_tolerance=1, y_tolerance=1) or "").strip()
        except Exception as exc:
            logger.warning("Fallback text extraction failed on page %d: %s", physical_page_number, exc)
            return ""

    def get_page_text(self, page_number: int) -> str:
        if page_number < 1 or page_number > self.total_pages:
            raise ValueError(f"Page number {page_number} out of range (1-{self.total_pages})")
        try:
            with pymupdf.open(self.file_path) as doc:
                return (doc.load_page(page_number - 1).get_text("text", sort=True) or "").strip()
        except Exception:
            return self._fallback_page_text(page_number)

    def get_total_pages(self) -> int:
        return self.total_pages

    def extract_text_range(self, start_page: int, end_page: int) -> str:
        if start_page < 1 or end_page > self.total_pages or start_page > end_page:
            raise ValueError(f"Invalid page range: {start_page}-{end_page}")
        parts = []
        for page_num, text, _ in self.extract_text_pages(start_page - 1, end_page):
            if text:
                parts.append(f"--- Page {page_num} ---\n{text}")
        return "\n\n".join(parts)


def extract_pdf_text(file_path: str, start_page: int = 1, end_page: Optional[int] = None) -> str:
    processor = PDFProcessor(file_path)
    if end_page is None:
        end_page = processor.get_total_pages()
    parts = []
    for _page_num, text, _ in processor.extract_text_pages(start_page - 1, end_page):
        if text:
            parts.append(text)
    return "\n\n".join(parts)
