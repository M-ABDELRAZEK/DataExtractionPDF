# PTS to SLD Data Extractor

A Windows desktop application that extracts structured data from Power Transformer Substation (PTS) PDF specifications and fills a fixed Single Line Diagram (SLD) Excel template. Uses local PDF processing with optional Groq Cloud AI for high-accuracy extraction, and generates GIS CAD draft plans for AutoCAD.

## 🎯 Overview

This tool automates the tedious manual process of reading multi-hundred-page PTS specification documents and populating SLD templates. It combines:

- **Fast PDF indexing** via PyMuPDF (handles 1000+ page documents)
- **Template-driven extraction** with 174 fixed SLD rows
- **Optional AI enhancement** via Groq Cloud (Llama/Mixtral/GPT-OSS models)
- **Audit trail** with page-level evidence for every extracted value
- **GIS CAD planning** for AutoCAD symbol placement (unconnected draft)

## ✨ Features

| Feature | Description |
|---------|-------------|
| **PDF → Markdown** | Converts PDF to auditable, section-oriented Markdown with physical page tags |
| **Template Contract** | Fixed A/B/C columns (Section/Component/Parameter) → generates D/E/F (Value/Pages/Reference) |
| **AI Extraction** | Groq Cloud API with strict JSON validation, evidence verification, and citation checking |
| **No Regex Values** | AI never receives raw PDF; only relevant Markdown sections with page context |
| **Checkpoint/Resume** | Atomic checkpoints every batch; survives crashes and rate limits |
| **CAD Draft** | Generates balanced GIS bay layouts with vendor DWG symbols (HYUNDAI) |
| **Windows Native** | AutoCAD COM automation with busy-retry logic; PowerShell HTTPS fallback for Groq |

## 📋 Requirements

### System
- **Windows 10/11** (required for AutoCAD COM integration)
- **Python 3.10+**
- **Full AutoCAD** (not LT) installed and licensed
- **Internet access** for Groq API (optional but recommended)

### Python Packages
```bash
pip install -r requirements.txt
```
- `customtkinter>=5.2.0` — Modern GUI
- `pdfplumber>=0.10.0` — Fallback PDF text extraction
- `pymupdf>=1.24.0` — Primary fast PDF engine
- `openpyxl>=3.1.0` — Excel template read/write
- `pywin32` — AutoCAD COM automation (Windows only)

### Groq API Key (Optional)
Set via one of:
1. **GUI** — Enter in "Groq API key" field (hidden, not saved)
2. **Environment** — `GROQ_API_KEY` in Windows Environment Variables
3. **Local `.env`** — File in project root (excluded from Git)

Get a free key at [console.groq.com](https://console.groq.com)

## 🚀 Quick Start

```bash
# 1. Clone and enter directory
cd DataExtractionPDF

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python main.py
```

### GUI Workflow
1. **Select PDF** — Choose your PTS specification PDF
2. **Select Output Dir** — Where Excel/JSON/Markdown will be saved
3. **Configure Options** (optional):
   - Page range (physical PDF pages 1..N)
   - Save intermediate Markdown for debugging
   - Enable Groq AI extraction
   - Set max AI rows for testing
   - Enable GIS CAD plan generation
4. **Click "Start Extraction"**
5. **Review Output** — Opens output folder on completion

## ⚙️ Configuration

Settings persist to `%USERPROFILE%\.pts_sld_extractor_settings.json`:

| Setting | Description |
|---------|-------------|
| Theme | System / Light / Dark |
| Color Theme | Blue / Green / Dark Blue |
| Default Output Directory | Base folder for outputs |
| Open Output After | Auto-open folder on completion |
| Save Intermediate | Keep page-level Markdown files |
| Log Level | DEBUG / INFO / WARNING / ERROR |

Access via **Settings** button in the GUI.

## 📁 Output Files

Every run creates a timestamped output folder with:

| File | Purpose |
|------|---------|
| `Extracted Data.xlsx` | Filled SLD template (columns D/E/F populated) |
| `extraction_results.json` | Complete results with evidence, pages, status |
| `extraction_audit.json` | AI-only audit trail |
| `template_schema.json` | Template contract (SHA-256 verified) |
| `remote_ends.json` | Discovered source substation remote ends |
| `api_connection_error.json` | Only on Groq failure |
| `extraction_checkpoint.json` | Resume point (auto-cleaned on success) |
| `intermediate/markdown/` | Page-tagged Markdown sections |
| `intermediate/api_debug/` | Raw Groq request/response per batch |
| `gis_plan.json` | CAD drawing plan (if enabled) |
| `GIS_DRAFT_UNCONNECTED_*.dwg` | AutoCAD draft (if "Assemble CAD Draft" clicked) |

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   PDF       │────▶│  Markdown        │────▶│  PDF Index      │
│  (PyMuPDF)  │     │  Sectionizer     │     │  (In-Memory)    │
└─────────────┘     └──────────────────┘     └────────┬────────┘
                                                      │
                        ┌─────────────────────────────┘
                        ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  SLD        │◀────│  Groq AI         │◀────│  Context        │
│  Template   │     │  Extractor       │     │  Retrieval      │
└─────────────┘     └──────────────────┘     └─────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  Excel Output   │
              │  + Audit JSON   │
              └────────┬────────┘
                       │
                       ▼ (optional)
              ┌─────────────────┐
              │  GIS CAD Plan   │────▶ AutoCAD .dwg Draft
              └─────────────────┘
```

### Key Design Principles
- **Physical page numbers only** — No reliance on printed page labels
- **Main SOW wins** — Project-specific content overrides generic standards
- **Evidence required** — Every AI value must cite verbatim text from allowed pages
- **NA for unresolved** — Never guess; flag for engineer review
- **Unconnected CAD** — Symbol placement only; no electrical routing

## 🔧 Troubleshooting

### Groq API 403 Forbidden
- **Cause**: Corporate proxy/gateway blocks `urllib` HTTPS
- **Fix**: App auto-falls back to PowerShell `Invoke-WebRequest` (same stack as browser)
- **Verify**: Click "Test Groq Connection" in Options panel

### AutoCAD "Busy" / RPC Errors
- **Cause**: AutoCAD modal dialog open or command active
- **Fix**: Close dialogs, press `Esc` in AutoCAD, retry
- **App retries** automatically for 45 seconds with message pumping

### No Values Extracted (All NA)
- Check `intermediate/markdown/` — was text extracted?
- Verify template `assets/Extracted Sheet Tempelate.xlsx` has "SLD" sheet
- Enable "Save Intermediate" and inspect Markdown for your sections

### Missing Vendor DWGs
- Place `.dwg` files in `assets/cad/vendors/HYUNDAI/`
- Required: `BUSBAR.dwg`, `BUSSECTION.dwg`, `BUSCOUPLER.dwg`, `INCOMER.dwg`, `F-INCOMER.dwg`, `OUTGOING.dwg`
- Run `build_cad_plan_from_json` to validate vertices via `VERTICES.xlsx`

## 📝 Template Format

The Excel template (`assets/Extracted Sheet Tempelate.xlsx`) must have:

| Column | Header | Type | Description |
|--------|--------|------|-------------|
| A | Section | Fixed | e.g., "GIS", "Power Transformer" |
| B | Component | Fixed | e.g., "Bays", "CB", "CT in OHL" |
| C | Parameter | Fixed | e.g., "OHL Feeder", "Short Circuit" |
| D | Drawing Value | **Output** | Extracted value or "NA" |
| E | PTS PDF Page | **Output** | Physical page number(s) |
| F | PTS Reference | **Output** | Clause / Appendix / TMSS ref |
| G | Note | Manual | Reserved for engineer notes |

Rows 1–2 are headers/project name. Data starts at row 3.

## 🧪 Development

### Run Tests (if test dir exists)
```bash
pytest tests/
```

### Code Structure
```
core/
  pdf_processor.py           # PyMuPDF extraction + OCR fallback
  sld_template_extractor.py  # Template I/O, PDFIndex, extraction logic
  pipeline_v3.py             # Main orchestration: Markdown → AI → Excel
  groq_extractor.py          # Groq client with validation + PS fallback
  markdown_sections.py       # PDF → sectioned Markdown + page segments
  template_contract.py       # JSON schema for template
  remote_ends.py             # Source substation discovery
gui/
  main_window.py             # CustomTkinter application
  settings_panel.py          # Persistent settings dialog
  progress_dialog.py         # Modal progress window
cad/
  autocad_backend.py         # COM automation with retry logic
  bay_layout.py              # Left/Right balanced bay scheduling
  geometry.py                # Vertex-aligned block placement
  gis_planner.py             # BOM + quantities from extraction JSON
utils/
  file_handler.py            # PDF validation, path utilities
```

## 📄 License

MIT License — see [LICENSE](LICENSE)

## 🙋 Support

- Check `logs/pdf_extractor.log` for detailed traces
- Review `api_connection_error.json` on Groq failures
- Open `extraction_results.json` to inspect per-row evidence

---

**Note**: The generated CAD draft is an **unconnected symbol layout** for engineer review. It is not an electrically validated SLD. All quantities and placements require manual verification against the source specification.