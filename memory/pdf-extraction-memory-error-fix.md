---
name: pdf-extraction-memory-error-fix
description: Fix for MemoryError during PDF text extraction due to font decompression issues
metadata:
  type: project
---

When processing large PDFs (e.g., 116 MB, 3091 pages), the application encountered a MemoryError: Unable to allocate output buffer during font decompression in pdfminer. This caused the extraction to crash.

The error occurred in the `extract_text_pages` method of `core/pdf_processor.py` when calling `page.extract_text(x_tolerance=1, y_tolerance=1)`.

Solution:
- Wrapped the text extraction call in a try-except block to catch exceptions per page.
- On failure, log a warning and return an empty string for that page's text, allowing extraction to continue.
- Applied similar error handling to the `get_page_text` method.
- Also added error handling for table extraction to prevent crashes from table extraction issues.

This change allows the application to skip problematic pages and continue processing the rest of the PDF.

After applying this fix, the extraction should proceed without crashing, though some pages may have missing text content.