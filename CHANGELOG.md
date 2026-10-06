# v2.0 - PTS to SLD Template Extraction

## Workflow
- Removed the generic Equipment Schedule export flow.
- The application now has one purpose: upload a PTS PDF and fill the fixed SLD Excel template.
- Fixed template columns: Section, Component, Parameter.
- Generated columns: Drawing Value, PTS PDF Page, PTS Reference.
- Note remains blank for manual engineering comments.
- Missing values are written as `NA` for Value/Page/Reference.
- Project name is extracted into cell A1; uploaded PDF filename is the fallback.

## Performance
- Replaced repeated full-PDF scans with a one-pass PyMuPDF page index.
- Physical PDF page numbers (viewer pages 1..N) are preserved directly.
- The 3091-page SHOAIBA-3 PTS indexed in about 28 seconds in the development environment; template-row resolution took about 6 seconds.

## Source priority
1. Main SOW
2. Project-specific appendices
3. Data schedules
4. Generic specifications

When the selected value is repeated on multiple relevant pages, the output page cell can contain multiple physical PDF page numbers separated by semicolons.

## Files
- `core/sld_template_extractor.py`: template loader, PDF page index and extraction engine.
- `core/pdf_processor.py`: fast one-pass PDF text extraction using PyMuPDF with pdfplumber fallback.
- `assets/Extracted Sheet Tempelate.xlsx`: fixed SLD template.
- `gui/main_window.py`: single PTS-to-SLD workflow.
- `gui/settings_panel.py`: simplified settings for the new workflow.
- `tests/test_sld_template_extractor.py`: regression tests for source priority, multi-page values, NA fallback and physical page numbering.

## v2.0.1 - 2026-10-06
- Fixed startup ImportError by restoring `show_settings()` in `gui/settings_panel.py`.
- Updated PyMuPDF usage from deprecated `fitz` import to `import pymupdf`.
- Updated startup dependency help to use `pip install -r requirements.txt`.
- Re-ran extractor unit tests: 5/5 passing.
