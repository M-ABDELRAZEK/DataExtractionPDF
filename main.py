"""
Main Entry Point
Application launcher for the PDF Data Extractor
"""

import sys
import os
import logging
from pathlib import Path

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

def setup_logging():
    """Setup application logging"""
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "pdf_extractor.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    """Main application entry point"""
    try:
        # Setup logging
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Starting PDF Data Extractor Application")

        # Import and run the GUI application
        from gui.main_window import PDFExtractorApp

        app = PDFExtractorApp()
        app.mainloop()

    except ImportError as e:
        print(f"Import error: {e}")
        print("Please ensure all required packages are installed:")
        print("  pip install customtkinter pdfplumber openpyxl")
        sys.exit(1)
    except Exception as e:
        print(f"Application error: {e}")
        logging.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()