# PTS to SLD Data Extractor

Desktop Python application that fills a fixed SLD engineering-data Excel template from an uploaded PTS / substation specification PDF.

## Current workflow

1. User selects a PTS PDF.
2. The application extracts every selected **physical PDF page once** and builds an in-memory text index.
3. The fixed Excel template in `assets/Extracted Sheet Tempelate.xlsx` supplies the first three columns:
   - Section
   - Component
   - Parameter
4. For each template row, the extractor searches the in-memory index and fills:
   - Drawing Value
   - PTS PDF Page
   - PTS Reference
5. If no supported value is found, all three generated fields are `NA`.
6. The Note column is left blank for manual engineering review.
7. Cell `A1` is replaced by the extracted project name. If no reliable project name is found, the uploaded PDF filename is used.

## Source priority

When conflicting values are found, the project-specific **Main SOW** has the highest priority, followed by project appendices, included data schedules, then generic specifications.

If the selected value is repeated on multiple relevant physical PDF pages, all matching page numbers are written to the page cell.

## PDF page numbering

`PTS PDF Page` always means the **physical page index in the uploaded PDF viewer (1..N)**. It does not depend on printed page labels such as `5 of 112`, appendix numbering, Roman numerals, or restarted section numbering. This makes the method consistent across different specification documents.

## Performance design

The PDF is not reopened for every template parameter. `PDFIndex` reads the selected page range once, stores normalized page text/tokens, and all row extraction operates against this cached index.

For a 3,000-page PDF and ~170 template rows, the expensive PDF parsing step is therefore ~3,000 page extractions rather than hundreds of thousands of repeated extractions.

## Main files

- `main.py` — application launcher
- `gui/main_window.py` — desktop UI and extraction orchestration
- `core/pdf_processor.py` — one-pass PDF text extraction
- `core/sld_template_extractor.py` — template loader, PDF index, source priority, value/reference extraction
- `assets/Extracted Sheet Tempelate.xlsx` — fixed SLD output structure

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Output contract

The generated workbook contains the `SLD` sheet only and preserves the template structure.

| Column | Field | Generated? |
|---|---|---|
| A | Section | Fixed from template |
| B | Component | Fixed from template |
| C | Parameter | Fixed from template |
| D | Drawing Value | Yes |
| E | PTS PDF Page | Yes |
| F | PTS Reference | Yes |
| G | Note | Blank / manual |

Engineering review is still required before using extracted values for issued-for-construction drawings.
