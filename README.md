# PDF Data Extractor

A modular Python application for extracting structured data from PDF files into formatted Excel workbooks with multiple tabs.

## Features

- **Modern GUI**: Built with CustomTkinter for a clean, professional interface
- **Robust PDF Parsing**: Uses pdfplumber for efficient text extraction from large PDFs (up to 3,000+ pages)
- **Rule-Based Extraction**: Configurable regex patterns for extracting specific data fields
- **Multi-Tab Excel Output**: Organizes extracted data into separate worksheets with proper formatting
- **Memory Efficient**: Processes PDFs page-by-page to handle large files without memory issues
- **Extensible Design**: Modular architecture makes it easy to add new extraction rules and Excel tabs

## Modules

### Core Components
- `config.py`: Centralized configuration, regex patterns, and styling definitions
- `core/pdf_processor.py`: Handles PDF text extraction using pdfplumber (streaming)
- `core/rules_engine.py`: Applies extraction rules using regex and contextual analysis
- `core/excel_formatter.py`: Creates formatted Excel workbooks with multiple tabs using openpyxl
- `utils/file_handler.py`: File validation, path handling, and utility functions

### GUI Components
- `gui/main_window.py`: Main application window with file selection, controls, and logging
- `gui/progress_dialog.py`: Progress feedback during long operations
- `gui/settings_panel.py`: Advanced configuration options

## Usage

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the application:
   ```bash
   python main.py
   ```

3. In the GUI:
   - Select a PDF file to process
   - Choose an output directory for the Excel file
   - Configure processing options (optional)
   - Click "Start Extraction" to begin

## Customization

### Adding New Extraction Rules
1. Add regex patterns to `config.EXTRACTION_PATTERNS`
2. The rules engine will automatically use new patterns
3. Adjust confidence scoring weights if needed in `config.py`

### Adding New Excel Tabs
1. Define template in `config.EXCEL_TEMPLATES`
2. Add data grouping logic in `group_data_by_type()` method in `main_window.py`
3. The excel formatter will automatically create and populate new worksheets

## Requirements

- Python 3.7+
- customtkinter
- pdfplumber
- openpyxl

See `requirements.txt` for specific versions.

## Design Principles

1. **Separation of Concerns**: UI, PDF processing, rules, and Excel generation are strictly separated
2. **Stream Processing**: PDFs processed page-by-page for memory efficiency
3. **Extensibility**: New features require minimal changes to existing code
4. **Error Handling**: Graceful handling of invalid files, missing data, and processing errors
5. **User Feedback**: Real-time progress indication and detailed logging

## Output Format

The Excel workbook contains:
- **Equipment_Schedule**: Main data with extracted fields and confidence scores
- **Summary**: Statistics about extractions by field and confidence level

Each worksheet includes:
- Styled headers with filtering enabled
- Frozen header row
- Auto-adjusted column widths
- Confidence-based cell coloring
- Proper data formatting (text, numbers, dates)