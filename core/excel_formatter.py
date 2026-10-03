"""
Excel Formatter Module
Handles creation and formatting of Excel workbooks using openpyxl
Supports multi-tab output with consistent styling
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
import config

logger = logging.getLogger(__name__)

class ExcelFormatter:
    """
    Formats and writes extracted data to Excel workbooks
    Creates multi-tab output with consistent styling
    """

    def __init__(self):
        """Initialize Excel formatter with styling from config"""
        self.wb = Workbook()
        # Remove default sheet
        if "Sheet" in self.wb.sheetnames:
            self.wb.remove(self.wb["Sheet"])

        # Initialize styling from config
        self._init_styles()
        logger.info("ExcelFormatter initialized")

    def _init_styles(self):
        """Initialize cell styles from configuration"""
        # Header style
        self.header_fill = PatternFill(
            fill_type="solid",
            start_color=config.COLORS["header_bg"],
            end_color=config.COLORS["header_bg"]
        )
        self.header_font = Font(
            name=config.FONTS["header"]["name"],
            size=config.FONTS["header"]["size"],
            bold=config.FONTS["header"]["bold"],
            color=config.FONTS["header"]["color"] if "color" in config.FONTS["header"] else config.COLORS["header_fg"]
        )

        # Data style
        self.data_fill = PatternFill(
            fill_type="solid",
            start_color=config.COLORS["data_bg"],
            end_color=config.COLORS["data_bg"]
        )
        self.data_font = Font(
            name=config.FONTS["data"]["name"],
            size=config.FONTS["data"]["size"],
            color=config.FONTS["data"]["color"] if "color" in config.FONTS["data"] else config.COLORS["data_fg"]
        )

        # Border style
        self.border = Border(
            left=Side(style=config.BORDER_STYLE["left"]["style"], color=config.BORDER_STYLE["left"]["color"]),
            right=Side(style=config.BORDER_STYLE["right"]["style"], color=config.BORDER_STYLE["right"]["color"]),
            top=Side(style=config.BORDER_STYLE["top"]["style"], color=config.BORDER_STYLE["top"]["color"]),
            bottom=Side(style=config.BORDER_STYLE["bottom"]["style"], color=config.BORDER_STYLE["bottom"]["color"])
        )

        # Alignment styles
        self.alignment_center = Alignment(
            horizontal=config.ALIGNMENTS["center"]["horizontal"],
            vertical=config.ALIGNMENTS["center"]["vertical"],
            wrap_text=config.ALIGNMENTS["center"]["wrap_text"]
        )
        self.alignment_left = Alignment(
            horizontal=config.ALIGNMENTS["left"]["horizontal"],
            vertical=config.ALIGNMENTS["left"]["vertical"],
            wrap_text=config.ALIGNMENTS["left"]["wrap_text"]
        )

        # Confidence-based fills
        self.confidence_fill_high = PatternFill(
            fill_type="solid",
            start_color=config.COLORS["confidence_high"],
            end_color=config.COLORS["confidence_high"]
        )
        self.confidence_fill_medium = PatternFill(
            fill_type="solid",
            start_color=config.COLORS["confidence_medium"],
            end_color=config.COLORS["confidence_medium"]
        )
        self.confidence_fill_low = PatternFill(
            fill_type="solid",
            start_color=config.COLORS["confidence_low"],
            end_color=config.COLORS["confidence_low"]
        )

    def create_worksheet(self, sheet_name: str, headers: List[str],
                        column_widths: List[int]) -> Any:
        """
        Create a new worksheet with headers and column widths

        Args:
            sheet_name (str): Name for the worksheet
            headers (List[str]): Column headers
            column_widths (List[int]): Width for each column

        Returns:
            Worksheet: The created worksheet object
        """
        ws = self.wb.create_sheet(title=sheet_name)

        # Write headers
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = self.header_fill
            cell.font = self.header_font
            cell.border = self.border
            cell.alignment = self.alignment_center

        # Set column widths
        for col_idx, width in enumerate(column_widths, start=1):
            column_letter = get_column_letter(col_idx)
            ws.column_dimensions[column_letter].width = width

        # Set header row height
        ws.row_dimensions[1].height = 25

        logger.debug(f"Created worksheet '{sheet_name}' with {len(headers)} columns")
        return ws

    def write_data_to_sheet(self, worksheet, data: List[Dict[str, Any]],
                           data_mapping: Dict[int, str],
                           start_row: int = 2) -> int:
        """
        Write data to a worksheet based on field mapping

        Args:
            worksheet: OpenPyXL worksheet object
            data (List[Dict]): List of data dictionaries
            data_mapping (Dict[int, str]): Maps column index to field name
            start_row (int): Row to start writing data (default: 2)

        Returns:
            int: Number of rows written
        """
        rows_written = 0

        for row_idx, data_item in enumerate(data, start=start_row):
            for col_idx, field_name in data_mapping.items():
                # Get the value from data item
                value = data_item.get(field_name, "")

                # Handle special formatting for certain fields
                formatted_value = self._format_cell_value(field_name, value)

                cell = worksheet.cell(row=row_idx, column=col_idx, value=formatted_value)
                cell.font = self.data_font
                cell.fill = self.data_fill
                cell.border = self.border
                cell.alignment = self.alignment_center

                # Apply confidence-based background if confidence field exists
                if "confidence" in data_item:
                    confidence = data_item["confidence"]
                    if confidence >= 0.8:
                        cell.fill = self.confidence_fill_high
                    elif confidence >= 0.5:
                        cell.fill = self.confidence_fill_medium
                    else:
                        cell.fill = self.confidence_fill_low

            rows_written += 1

        logger.debug(f"Wrote {rows_written} rows to worksheet '{worksheet.title}'")
        return rows_written

    def _format_cell_value(self, field_name: str, value: Any) -> Any:
        """
        Apply special formatting to cell values based on field type

        Args:
            field_name (str): Name of the field
            value (Any): Raw value

        Returns:
            Any: Formatted value
        """
        if value is None or value == "":
            return ""

        # Convert to string if not already
        if not isinstance(value, str):
            value = str(value)

        # Special handling for certain fields
        if field_name == "page_number":
            try:
                return int(value)
            except (ValueError, TypeError):
                return value

        elif field_name in ["quantity", "confidence"]:
            try:
                # Try to convert to number
                if "." in value:
                    return float(value)
                else:
                    return int(value)
            except (ValueError, TypeError):
                return value

        elif field_name == "rating":
            # No truncation - preserve full rating/specification data
            return value

        return value

    def add_auto_filter(self, worksheet, last_row: int, last_col: int):
        """
        Add auto-filter to a worksheet

        Args:
            worksheet: Worksheet to add filter to
            last_row (int): Last row with data
            last_col (int): Last column with data
        """
        if last_row > 1 and last_col > 0:
            last_column_letter = get_column_letter(last_col)
            worksheet.auto_filter.ref = f"A1:{last_column_letter}{last_row}"
            logger.debug(f"Added auto-filter to range A1:{last_column_letter}{last_row}")

    def freeze_header_row(self, worksheet):
        """
        Freeze the header row (first row) of a worksheet

        Args:
            worksheet: Worksheet to freeze
        """
        worksheet.freeze_panes = "A2"
        logger.debug(f"Frozen header row in worksheet '{worksheet.title}'")

    def create_summary_sheet(self, statistics: Dict[str, Any]) -> Any:
        """
        Create a summary worksheet with extraction statistics

        Args:
            statistics (Dict): Statistics data from rules engine

        Returns:
            Worksheet: The summary worksheet
        """
        # Use template from config if available, otherwise create default
        if "Summary" in config.EXCEL_TEMPLATES:
            template = config.EXCEL_TEMPLATES["Summary"]
            headers = template["headers"]
            column_widths = template["column_widths"]
        else:
            # Default summary template
            headers = [
                "Data Type",
                "Total Found",
                "High Confidence (>=0.8)",
                "Medium Confidence (0.5-0.8)",
                "Low Confidence (<0.5)",
                "First Seen Page",
                "Last Seen Page"
            ]
            column_widths = [20, 12, 12, 12, 12, 15, 15]

        ws = self.create_worksheet("Summary", headers, column_widths)

        # Write statistics data
        row_idx = 2
        if "by_field" in statistics and statistics["by_field"]:
            for field_name, field_data in statistics["by_field"].items():
                # Get confidence breakdown for this field
                high_count = 0
                medium_count = 0
                low_count = 0
                pages = field_data.get("pages", [])

                total_count = field_data.get("count", 0)
                high_count = field_data.get("high", 0)
                medium_count = field_data.get("medium", 0)
                low_count = field_data.get("low", 0)

                cell = ws.cell(row=row_idx, column=1, value=field_name)
                cell = ws.cell(row=row_idx, column=2, value=total_count)
                cell = ws.cell(row=row_idx, column=3, value=high_count)
                cell = ws.cell(row=row_idx, column=4, value=medium_count)
                cell = ws.cell(row=row_idx, column=5, value=low_count)
                cell = ws.cell(row=row_idx, column=6, value=min(pages) if pages else "")
                cell = ws.cell(row=row_idx, column=7, value=max(pages) if pages else "")

                # Apply styling
                for col_idx in range(1, len(headers) + 1):
                    cell = ws.cell(row=row_idx, column=col_idx)
                    cell.font = self.data_font
                    cell.fill = self.data_fill
                    cell.border = self.border
                    cell.alignment = self.alignment_center

                row_idx += 1

        # Add totals row
        if row_idx > 2:
            cell = ws.cell(row=row_idx, column=1, value="TOTALS")
            cell.font = Font(bold=True)
            # Sum the total found column
            total_found = statistics.get("total_extractions", 0)
            cell = ws.cell(row=row_idx, column=2, value=total_found)
            cell.font = Font(bold=True)

            # Apply styling to totals row
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(fill_type="solid", start_color="D9E1F2", end_color="D9E1F2")
                cell.border = self.border
                cell.alignment = self.alignment_center

        # Apply worksheet formatting
        self.freeze_header_row(ws)
        self.add_auto_filter(ws, row_idx, len(headers))

        logger.info("Created summary worksheet")
        return ws

    def save_workbook(self, file_path: str):
        """
        Save the workbook to file

        Args:
            file_path (str): Path to save the Excel file
        """
        try:
            self.wb.save(file_path)
            logger.info(f"Workbook saved successfully to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save workbook: {e}")
            raise

    def get_workbook(self) -> Workbook:
        """
        Get the workbook object for direct manipulation

        Returns:
            Workbook: The openpyxl Workbook object
        """
        return self.wb

# Convenience functions
def create_excel_workbook() -> ExcelFormatter:
    """
    Convenience function to create a new Excel formatter

    Returns:
        ExcelFormatter: New formatter instance
    """
    return ExcelFormatter()

def format_and_save_data(data: Dict[str, List[Dict[str, Any]]],
                        output_path: str,
                        statistics: Optional[Dict[str, Any]] = None):
    """
    Convenience function to format data and save to Excel

    Args:
        data (Dict[str, List[Dict]]): Data organized by worksheet name
        output_path (str): Path to save Excel file
        statistics (Optional[Dict]): Statistics for summary sheet
    """
    formatter = ExcelFormatter()

    # Add each data set to its respective worksheet
    for sheet_name, sheet_data in data.items():
        if sheet_name in config.EXCEL_TEMPLATES:
            template = config.EXCEL_TEMPLATES[sheet_name]
            headers = template["headers"]
            column_widths = template["column_widths"]
            data_mapping = template["data_mapping"]

            # Create worksheet
            ws = formatter.create_worksheet(sheet_name, headers, column_widths)

            # Write data
            if sheet_data:
                formatter.write_data_to_sheet(ws, sheet_data, data_mapping)

            # Apply formatting
            last_row = len(sheet_data) + 1 if sheet_data else 1
            formatter.freeze_header_row(ws)
            formatter.add_auto_filter(ws, last_row, len(headers))
        else:
            logger.warning(f"No template found for sheet '{sheet_name}', skipping")

    # Add summary sheet if statistics provided
    if statistics:
        formatter.create_summary_sheet(statistics)

    # Save workbook
    formatter.save_workbook(output_path)

    logger.info(f"Excel workbook created and saved to {output_path}")