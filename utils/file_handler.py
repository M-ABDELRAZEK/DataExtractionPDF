"""
Utility functions for file handling and validation
"""

import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def validate_pdf_file(file_path):
    """
    Validate that a file is a readable PDF

    Args:
        file_path (str or Path): Path to the file to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        path = Path(file_path)

        # Check if file exists
        if not path.exists():
            return False, f"File does not exist: {path}"

        # Check if it's a file (not a directory)
        if not path.is_file():
            return False, f"Path is not a file: {path}"

        # Check file extension
        if path.suffix.lower() != '.pdf':
            return False, f"File is not a PDF: {path.suffix}"

        # Check file size
        file_size_mb = path.stat().st_size / (1024 * 1024)
        from config import MAX_FILE_SIZE_MB
        if file_size_mb > MAX_FILE_SIZE_MB:
            return False, f"File too large: {file_size_mb:.1f} MB (max {MAX_FILE_SIZE_MB} MB)"

        # Check if file is readable
        if not os.access(path, os.R_OK):
            return False, f"File is not readable: {path}"

        # Try to read first few bytes to check if it's a valid PDF
        with open(path, 'rb') as f:
            header = f.read(5)
            if header != b'%PDF-':
                return False, "File does not appear to be a valid PDF"

        logger.info(f"PDF validation passed: {path} ({file_size_mb:.1f} MB)")
        return True, ""

    except Exception as e:
        logger.error(f"Error validating PDF file: {e}")
        return False, f"Validation error: {str(e)}"

def get_output_filename(input_path, suffix="", extension=".xlsx"):
    """
    Generate output filename based on input file

    Args:
        input_path (str or Path): Input PDF file path
        suffix (str): Optional suffix to add to filename
        extension (str): File extension (default: .xlsx)

    Returns:
        str: Generated output filename (without directory path)
    """
    input_path = Path(input_path)
    stem = input_path.stem
    if suffix:
        stem = f"{stem}_{suffix}"
    return f"{stem}{extension}"

def ensure_directory(directory_path):
    """
    Ensure a directory exists, create if it doesn't

    Args:
        directory_path (str or Path): Directory path to ensure exists

    Returns:
        Path: The directory path
    """
    path = Path(directory_path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def clean_filename(filename):
    """
    Clean a string to be safe for use as a filename

    Args:
        filename (str): String to clean

    Returns:
        str: Cleaned filename
    """
    # Remove or replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')

    # Remove leading/trailing spaces and dots
    filename = filename.strip(' .')

    # Ensure filename is not empty
    if not filename:
        filename = "unnamed"

    return filename

def format_file_size(size_bytes):
    """
    Format file size in human readable format

    Args:
        size_bytes (int): Size in bytes

    Returns:
        str: Formatted size string
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f"{size_bytes:.1f} {size_names[i]}"