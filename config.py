"""Application configuration for the PTS → SLD template extractor."""

from pathlib import Path

APP_NAME = "PTS to SLD Data Extractor"
APP_VERSION = "2.0.0"
DEFAULT_OUTPUT_DIR = Path.cwd() / "output"
SETTINGS_FILE = Path.home() / ".pts_sld_extractor_settings.json"
MAX_FILE_SIZE_MB = 500

PROJECT_ROOT = Path(__file__).resolve().parent
SLD_TEMPLATE_PATH = PROJECT_ROOT / "assets" / "Extracted Sheet Tempelate.xlsx"
DEFAULT_OUTPUT_FILENAME = "Extracted Data.xlsx"
