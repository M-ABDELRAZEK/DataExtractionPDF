"""
PDF Processing Module
Handles reading and extracting text from PDF files using pdfplumber
Designed for memory-efficient processing of large PDFs
"""

import pdfplumber
import logging
from pathlib import Path
from typing import Generator, Tuple, Optional
import time

logger = logging.getLogger(__name__)

class PDFProcessor:
    """
    Processes PDF files and extracts text content
    Uses streaming approach to handle large files efficiently
    """

    def __init__(self, file_path: str):
        """
        Initialize PDF processor

        Args:
            file_path (str): Path to the PDF file
        """
        self.file_path = Path(file_path)
        self.total_pages = 0
        self._validate_file()

    def _validate_file(self):
        """Validate that the PDF file exists and is readable"""
        if not self.file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {self.file_path}")

        if not self.file_path.is_file():
            raise ValueError(f"Path is not a file: {self.file_path}")

        if self.file_path.suffix.lower() != '.pdf':
            raise ValueError(f"File is not a PDF: {self.file_path}")

        # Quick validation by trying to open
        try:
            with pdfplumber.open(self.file_path) as pdf:
                self.total_pages = len(pdf.pages)
                if self.total_pages == 0:
                    raise ValueError("PDF contains no pages")
        except Exception as e:
            raise ValueError(f"Invalid or corrupted PDF file: {e}")

        logger.info(f"PDF initialized: {self.file_path.name} ({self.total_pages} pages)")

    def extract_text_pages(self,
                         start_page: int = 0,
                         end_page: Optional[int] = None,
                         extract_tables: bool = False) -> Generator[Tuple[int, str, Optional[list]], None, None]:
        """
        Extract text from PDF pages one by one (generator for memory efficiency)

        Args:
            start_page (int): Starting page index (0-based)
            end_page (Optional[int]): Ending page index (exclusive), None for all pages
            extract_tables (bool): Whether to also extract tables

        Yields:
            Tuple[int, str, Optional[list]]: (page_number, text_content, tables_data)
        """
        if end_page is None:
            end_page = self.total_pages
        else:
            end_page = min(end_page, self.total_pages)

        if start_page < 0 or start_page >= self.total_pages:
            raise ValueError(f"Start page {start_page} out of range (0-{self.total_pages-1})")

        if end_page <= start_page:
            raise ValueError(f"End page {end_page} must be greater than start page {start_page}")

        logger.info(f"Extracting pages {start_page+1} to {end_page} of {self.total_pages}")

        try:
            with pdfplumber.open(self.file_path) as pdf:
                for page_num in range(start_page, end_page):
                    page = pdf.pages[page_num]

                    # Extract text
                    text = page.extract_text(x_tolerance=1, y_tolerance=1) or ""

                    # Extract tables if requested
                    tables = None
                    if extract_tables:
                        try:
                            tables = page.extract_tables()
                        except Exception as e:
                            logger.warning(f"Could not extract tables from page {page_num+1}: {e}")
                            tables = []

                    # Yield page number (1-based for display), text, and tables
                    yield (page_num + 1, text.strip(), tables)

                    # Log progress every 50 pages
                    if (page_num + 1) % 50 == 0:
                        logger.debug(f"Processed {page_num + 1} pages")

        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise

    def get_page_text(self, page_number: int) -> str:
        """
        Get text from a specific page (1-based)

        Args:
            page_number (int): Page number (1-based)

        Returns:
            str: Text content of the page
        """
        if page_number < 1 or page_number > self.total_pages:
            raise ValueError(f"Page number {page_number} out of range (1-{self.total_pages})")

        try:
            with pdfplumber.open(self.file_path) as pdf:
                page = pdf.pages[page_number - 1]
                return page.extract_text(x_tolerance=1, y_tolerance=1) or ""
        except Exception as e:
            logger.error(f"Error extracting text from page {page_number}: {e}")
            return ""

    def get_total_pages(self) -> int:
        """Get total number of pages in the PDF"""
        return self.total_pages

    def extract_text_range(self, start_page: int, end_page: int) -> str:
        """
        Extract text from a range of pages and combine into single string

        Args:
            start_page (int): Starting page (1-based, inclusive)
            end_page (int): Ending page (1-based, inclusive)

        Returns:
            str: Combined text from all pages in range
        """
        if start_page < 1 or end_page > self.total_pages or start_page > end_page:
            raise ValueError(f"Invalid page range: {start_page}-{end_page}")

        text_parts = []
        for page_num, text, _ in self.extract_text_pages(start_page-1, end_page):
            if text:
                text_parts.append(f"--- Page {page_num} ---\n{text}")

        return "\n\n".join(text_parts)

# Convenience function for simple use cases
def extract_pdf_text(file_path: str,
                    start_page: int = 1,
                    end_page: Optional[int] = None) -> str:
    """
    Simple function to extract text from PDF (loads all into memory - use for small PDFs)

    Args:
        file_path (str): Path to PDF file
        start_page (int): Starting page (1-based)
        end_page (Optional[int]): Ending page (1-based, inclusive), None for all pages

    Returns:
        str: Extracted text
    """
    processor = PDFProcessor(file_path)

    if end_page is None:
        end_page = processor.get_total_pages()

    text_parts = []
    for page_num, text, _ in processor.extract_text_pages(start_page-1, end_page):
        if text:
            text_parts.append(text)

    return "\n\n".join(text_parts)