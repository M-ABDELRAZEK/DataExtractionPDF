"""
Configuration module for PDF Extractor Application
Contains constants, regex patterns, column mappings, and styling definitions
"""

import re
from pathlib import Path

# ==========================
# APPLICATION CONSTANTS
# ==========================
APP_NAME = "PDF Data Extractor"
APP_VERSION = "1.0.0"
DEFAULT_OUTPUT_DIR = Path.cwd() / "output"
SETTINGS_FILE = Path.home() / ".pdf_data_extractor_settings.json"
MAX_FILE_SIZE_MB = 500  # Maximum PDF size to process

# ==========================
# PDF PROCESSING SETTINGS
# ==========================
PDF_EXTRACTION_MODE = "text"  # Options: "text", "tables", "both"
PAGES_PER_BATCH = 100  # Process pages in batches for progress reporting

# ==========================
# EXTRACTION RULES (REGEX PATTERNS)
# ==========================
# Define patterns for different data types you want to extract
EXTRACTION_PATTERNS = {
    # Equipment identification patterns - FIXED to reduce false positives
    "equipment_id": [
        r"(?:Equipment\s*ID|Eq\.?\s*ID|Tag\s*No\.?|Asset\s*No\.?|Equipment\s*Tag)[\s#]*[:\-]?\s*([A-Z0-9][A-Z0-9\-_.]{2,})",
        r"(?:EQ\-|TAG\-|Asset\-|Item\-)\s*([A-Z0-9][A-Z0-9\-_.]{2,})",
        r"\b([A-Z]{2,4}\d{3,}[A-Z0-9\-_]*)\b",  # Common equipment ID patterns like AB123, XYZ456A
        r"\b([A-Z]{1,3}-\d{2,4}[A-Z0-9]*)\b",   # Patterns like T-123, AB-456
    ],

    # Rating/specification patterns - FIXED to capture electrical ratings
    "rating": [
        # Electrical power system ratings
        r"(\d+(?:\.\d+)?\s*kV\b)",                                          # Voltage: 115 kV, 13.8 kV
        r"(\d+(?:\.\d+)?\s*kA\b)",                                          # Current: 40 kA, 25 kA
        r"(\d+(?:\.\d+)?\s*A\b)",                                           # Current: 1200 A, 2000 A
        r"(\d+(?:\.\d+)?\s*MW\b)",                                          # Power: 50 MW, 100 MW
        r"(\d+(?:\.\d+)?\s*MVA\b)",                                         # Apparent power: 50 MVA
        r"(\d+(?:\.\d+)?\s*Hz\b)",                                          # Frequency: 50 Hz, 60 Hz
        r"(\d+(?:\.\d+)?\s*%\b)",                                           # Percent: 5.5%, 10%
        r"(?:Rating|Specif(?:ication)?|Capacity|Voltage|Current|Power|Impedance|Frequency)[\s:]*([^\n\r]{5,60})",
        r"(?:Class\s*\d+[\s:]*)([^\n\r]{10,50})",
        r"(?:Operating\s*(?:Voltage|Current|Power|Frequency|Impedance))[\s:]*([^\n\r]{5,50})",
        r"(?:Short\s*circuit|Impedance|Reactance|Resistance)[\s:]*([^\n\r]{5,50})",
        r"(?:Nominal\s*(?:Voltage|Current|Power))[\s:]*([^\n\r]{5,50})",
    ],

    # Quantity patterns - ENHANCED for equipment counts
    "quantity": [
        r"(?:Quantity|Qty|Q\.?\s*No\.?|Total\s*Qty)[\s:]*(\d+(?:\.\d+)?)\s*(?:units?|pcs?|ea|sets?|pcs)",
        r"(\d+(?:\.\d+)?)\s*(?:units?|pcs?|pieces?|ea|sets?)\b",
        r"(?:Qty\s*[:=]?\s*)(\d+(?:\.\d+))",
        r"(\d+)\s*(?:x\s*)?(?:pcs?|units?|ea)",
        r"(?:Qty\s*[:=]?\s*)(\d+(?:\.\d+)?)\b",
        r"\b(\d+)\s*(?:transformers?|breakers?|switches?|panels?|relays?|cables?)\b",
        r"\b(\d+)\s*(?:CTs?|PTs?|CBs?)\b",  # Common equipment abbreviations
    ],

    # Standard/reference patterns - FIXED to prevent over-capturing
    "standard": [
        # More specific standard patterns with better boundaries
        r"(?:Standard|Std\.?|Ref\.?|Spec\.?)\s*[:\-=]?\s*([A-Z]{2,5}\s*\d{1,4}(?:\.\d+){0,2}[A-Z]*)",
        r"(?:IEC\s+)\s*(\d{2,4}(?:\.\d+){1,2})",
        r"(?:IEEE\s+)\s*(\d{2,4}(?:\.\d+){0,2})",
        r"(?:ANSI\s+)\s*(\d{2,4}(?:\.\d+){0,2})",
        r"(?:ASME\s+)\s*(\d{2,4}(?:\.\d+){0,2})",
        r"(?:ASTM\s+)\s*(\d{2,4}(?:\.\d+){0,2})",
        r"(?:BS\s+)\s*(\d{2,4}(?:\.\d+){0,2})",
        r"(?:ISO\s+)\s*(\d{2,4}(?:\.\d+){0,2})",
        r"(?:CSA\s+)\s*(\d{2,4})",
        r"(?:VDS\s+)\s*(\d{2,4})",
        # Also catch common standalone standard references
        r"\b(IEC\s*\d{2,4}(?:\.\d+){1,2})\b",
        r"\b(IEEE\s*\d{2,4}(?:\.\d+){0,2})\b",
        r"\b(ANSI\s*\d{2,4}(?:\.\d+){0,2})\b",
        r"\b(ASME\s*\d{2,4}(?:\.\d+){0,2})\b",
        r"\b(IEC\s*\d{2,4})\b",  # IEC 61850, IEC 60870, etc.
    ],

    # Source document/section patterns - ENHANCED for Part/Section extraction
    "source_doc": [
        r"(?:Source\s*Doc(?:ument)?|Doc\.?\s*No\.?|Drawing\s*No\.)[\s:]*([^\n\r]{5,50})",
        r"(?:Part\s*[IVX]+[\s\-]*)([A-Z0-9][A-Z0-9\s\-._]{0,40})",
        r"(?:Drawing\s*No\.?|Doc\.?\s*No\.?)[\s:]*([A-Z0-9][A-Z0-9\-._]{0,30})",
        r"(?:Rev\.?\s*[\dA-Z]+)[\s\-]*([A-Z0-9][A-Z0-9\s\-._]{0,20})",
        r"(?:TCS\s*[\-\s]?\d+(?:\.\d+)*)",
        r"\b(Part\s*[IVX]+)\b",
        r"\b(TCS\s*-\s*\d+(?:\.\d+)*)\b",
    ],

    # Section and clause patterns used by the Excel schedule
    "section_clause": [
        r"\b(Section\s+\d+(?:\.\d+)*)\b",
        r"\b(Clause\s+\d+(?:\.\d+)*)\b",
        r"\b(TCS\s*-\s*\d+(?:\.\d+)*)\b",
    ],

    # Equipment type patterns - to capture equipment descriptions
    "equipment_type": [
        r"(?:Equipment\s*Type|Type\s*of\s*Equipment|Item\s*Description|Equipment(?!\s*(?:ID|Tag)))[\s:]*([^\n\r]{5,100})",
        r"(?:Power\s*Transformer|Circuit\s*Breaker|Current\s*Transformer|Voltage\s*Transformer|GIS\s*Panel|Relay\s*Panel|Cable|Disconnect\s*Switch|Busbar|Isolator|Surge\s*Arrester|Reactors?|Capacitors?)",
        r"\b(?:Transformer|Breaker|CT|VT|CB|GIS|Relay|Switch|Motor|Generator|Capacitor|Reactor|Arrester|Isolator)\b",
        r"(?:MV\s*|HV\s*|LV\s*)?(?:Switchgear|Panel|Board)",
        r"\b(Power\s*Transformer|Circuit\s*Breaker|Current\s*Transformer|Voltage\s*Transformer|GIS\s*Panel|Relay\s*Panel|Cable|Disconnect\s*Switch|Busbar|Isolator|Surge\s*Arrester)\b",
        r"\b(Transformers?|Breakers?|Switches?|Panels?|Relays?)\b",
    ],

    # Notes/status patterns - KEEPING as they worked well
    "notes": [
        r"(?:Notes?|Status|Remarks?)[\s:]*([^\n\r]{0,200})",
        r"\b(VERIFIED|PENDING|APPROVED|REVIEW\s*REQUIRED|REJECTED|CERTIFIED|TESTED|COMMISSIONED)\b",
    ],

    # Page number (for reference) - KEEPING as is
    "page_ref": [
        r"(?:Page\s*)(\d+)",
        r"(?:Pg\.?\s*)(\d+)",
    ]
}

# ==========================
# EXCEL TEMPLATE DEFINITIONS
# ==========================
# Define the structure for each Excel worksheet to match user's desired format
EXCEL_TEMPLATES = {
    "Equipment_Schedule": {
        "headers": [
            "Source Part",
            "Clause/Section",
            "PDF Page",
            "Equipment/Item",
            "Quantity",
            "Rating/Specification",
            "Standard Reference",
            "Notes"
        ],
        "column_widths": [25, 18, 15, 35, 13, 100, 22, 35],  # Matching user's Sheet Generation.py
        "data_mapping": {
            # Maps Excel column index (1-based) to data field
            1: "source_doc",      # Source Part
            2: "section_clause",  # Clause/Section (will enhance patterns or create this field)
            3: "page_number",     # PDF Page
            4: "equipment_item",  # Equipment/Item (combination field we'll create in processing)
            5: "quantity",        # Quantity
            6: "rating",          # Rating/Specification
            7: "standard",        # Standard Reference
            8: "notes"            # Notes
        }
    },

    "Summary": {
        "headers": [
            "Data Type",
            "Total Found",
            "High Confidence (>=0.8)",
            "Medium Confidence (0.5-0.8)",
            "Low Confidence (<0.5)",
            "First Seen Page",
            "Last Seen Page"
        ],
        "column_widths": [20, 12, 12, 12, 12, 15, 15],
        "data_mapping": {}  # Will be populated dynamically
    }
}

# ==========================
# STYLING DEFINITIONS
# ==========================
# Colors in hex format
COLORS = {
    "header_bg": "1F4E78",      # Dark blue
    "header_fg": "FFFFFF",      # White
    "data_bg": "F8F9FA",        # Light gray
    "data_fg": "000000",        # Black
    "border": "BFBFBF",         # Gray
    "confidence_high": "C6EFCE", # Light green
    "confidence_medium": "FFEB9C", # Light yellow
    "confidence_low": "F4CCCC",  # Light red
}

# Font styles
FONTS = {
    "header": {"name": "Calibri", "size": 12, "bold": True},
    "data": {"name": "Calibri", "size": 11},
    "summary": {"name": "Calibri", "size": 10, "bold": True}
}

# Alignment styles
ALIGNMENTS = {
    "center": {"horizontal": "center", "vertical": "center", "wrap_text": True},
    "left": {"horizontal": "left", "vertical": "center", "wrap_text": True},
    "right": {"horizontal": "right", "vertical": "center", "wrap_text": True}
}

# Border styles
BORDER_STYLE = {
    "left": {"style": "thin", "color": COLORS["border"]},
    "right": {"style": "thin", "color": COLORS["border"]},
    "top": {"style": "thin", "color": COLORS["border"]},
    "bottom": {"style": "thin", "color": COLORS["border"]}
}

# ==========================
# CONFIDENCE SCORING
# ==========================
# Weights for different extraction methods (can be adjusted)
CONFIDENCE_WEIGHTS = {
    "regex_match": 0.8,
    "keyword_proximity": 0.6,
    "length_score": 0.4,
    "context_score": 0.5
}

# Minimum confidence threshold to include data
MIN_CONFIDENCE_THRESHOLD = 0.3

# ==========================
# FILE PATHS
# ==========================
def get_output_dir():
    """Get or create output directory"""
    DEFAULT_OUTPUT_DIR.mkdir(exist_ok=True)
    return DEFAULT_OUTPUT_DIR

def get_temp_dir():
    """Get temporary directory for processing"""
    temp_dir = Path.cwd() / "temp"
    temp_dir.mkdir(exist_ok=True)
    return temp_dir