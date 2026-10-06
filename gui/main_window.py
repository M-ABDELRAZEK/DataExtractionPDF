"""
Main Window Module
Contains the main application window and GUI components
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import queue
import json
import logging
from pathlib import Path
import sys
import os

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.pdf_processor import PDFProcessor
from core.sld_template_extractor import PDFIndex, SLDTemplate, SLDTemplateExtractor
from utils.file_handler import validate_pdf_file, get_output_filename, ensure_directory
from gui.settings_panel import show_settings
import config

logger = logging.getLogger(__name__)

class PDFExtractorApp(ctk.CTk):
    """
    Main application window for PDF Data Extractor
    """

    def __init__(self):
        super().__init__()

        # Configure window
        self.title("PTS to SLD Data Extractor v2.0")
        self.geometry("900x700")
        self.minsize(800, 600)

        # Set appearance mode and color theme
        saved_settings = self._load_saved_settings()
        general_settings = saved_settings.get("general", {})
        ctk.set_appearance_mode(general_settings.get("theme", "System"))
        ctk.set_default_color_theme(general_settings.get("color_theme", "blue"))

        # Initialize variables

        self.pdf_file_path = tk.StringVar()
        self.output_dir_path = tk.StringVar(
            value=general_settings.get("default_output_dir", str(Path.cwd() / "output"))
        )
        self.is_processing = False
        self.processing_thread = None
        self.message_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.processing_options = {}
        self.saved_settings = saved_settings

        # Create output directory
        ensure_directory(self.output_dir_path.get())

        # Setup GUI
        self.setup_ui()
        self.setup_grid_layout()
        self.start_queue_processor()

        logger.info("PDF Extractor Application initialized")

    def setup_ui(self):
        """Setup all user interface components"""
        # Create main frames
        self.create_header_frame()
        self.create_file_selection_frame()
        self.create_options_frame()
        self.create_control_frame()
        self.create_progress_frame()
        self.create_log_frame()

    def setup_grid_layout(self):
        """Configure grid layout for responsive design"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # Header
        self.grid_rowconfigure(1, weight=0)  # File selection
        self.grid_rowconfigure(2, weight=0)  # Options
        self.grid_rowconfigure(3, weight=0)  # Controls
        self.grid_rowconfigure(4, weight=0)  # Progress
        self.grid_rowconfigure(5, weight=1)  # Log (expandable)

    def create_header_frame(self):
        """Create application header"""
        self.header_frame = ctk.CTkFrame(self, height=80)
        self.header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.header_frame.grid_propagate(False)

        # App title
        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="PTS to SLD Data Extractor",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=20)

        # App subtitle
        self.subtitle_label = ctk.CTkLabel(
            self.header_frame,
            text="Fill a fixed SLD Excel template directly from an uploaded PTS PDF",
            font=ctk.CTkFont(size=14)
        )
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

    def create_file_selection_frame(self):
        """Create file selection components"""
        self.file_frame = ctk.CTkFrame(self)
        self.file_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.file_frame.grid_columnconfigure(1, weight=1)

        # PDF File Selection
        self.pdf_label = ctk.CTkLabel(self.file_frame, text="PDF File:", font=ctk.CTkFont(weight="bold"))
        self.pdf_label.grid(row=0, column=0, padx=(20, 10), pady=15, sticky="w")

        self.pdf_entry = ctk.CTkEntry(
            self.file_frame,
            textvariable=self.pdf_file_path,
            width=400,
            placeholder_text="Select a PDF file to process..."
        )
        self.pdf_entry.grid(row=0, column=1, padx=10, pady=15, sticky="ew")

        self.pdf_browse_btn = ctk.CTkButton(
            self.file_frame,
            text="Browse",
            width=80,
            command=self.browse_pdf_file
        )
        self.pdf_browse_btn.grid(row=0, column=2, padx=(10, 20), pady=15)

        # Output Directory Selection
        self.output_label = ctk.CTkLabel(self.file_frame, text="Output Dir:", font=ctk.CTkFont(weight="bold"))
        self.output_label.grid(row=1, column=0, padx=(20, 10), pady=15, sticky="w")

        self.output_entry = ctk.CTkEntry(
            self.file_frame,
            textvariable=self.output_dir_path,
            width=400,
            placeholder_text="Select output directory for Excel files..."
        )
        self.output_entry.grid(row=1, column=1, padx=10, pady=15, sticky="ew")

        self.output_browse_btn = ctk.CTkButton(
            self.file_frame,
            text="Browse",
            width=80,
            command=self.browse_output_dir
        )
        self.output_browse_btn.grid(row=1, column=2, padx=(10, 20), pady=15)

    def create_options_frame(self):
        """Create processing options for the fixed SLD template workflow."""
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.options_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.options_title = ctk.CTkLabel(
            self.options_frame,
            text="Processing Options",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.options_title.grid(row=0, column=0, columnspan=3, padx=20, pady=(15, 10), sticky="w")

        self.save_intermediate_var = tk.BooleanVar(
            value=self.saved_settings.get("pdf_processing", {}).get("save_intermediate", False)
        )
        self.save_intermediate_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Save Intermediate Text",
            variable=self.save_intermediate_var
        )
        self.save_intermediate_cb.grid(row=1, column=0, padx=20, pady=10, sticky="w")

        self.open_output_var = tk.BooleanVar(
            value=self.saved_settings.get("general", {}).get("open_output_after", True)
        )
        self.open_output_cb = ctk.CTkCheckBox(
            self.options_frame,
            text="Open Output Folder When Done",
            variable=self.open_output_var
        )
        self.open_output_cb.grid(row=1, column=1, padx=20, pady=10, sticky="w")

        workflow_label = ctk.CTkLabel(
            self.options_frame,
            text="Workflow: Fixed SLD Template → Drawing Value / PTS Page / PTS Reference",
            text_color=("#1F4E78", "#8DB8E8")
        )
        workflow_label.grid(row=1, column=2, padx=20, pady=10, sticky="w")

        self.page_range_label = ctk.CTkLabel(
            self.options_frame,
            text="Physical PDF Page Range (optional):",
            font=ctk.CTkFont(weight="bold")
        )
        self.page_range_label.grid(row=2, column=0, padx=20, pady=(10, 15), sticky="w")

        self.page_range_frame = ctk.CTkFrame(self.options_frame)
        self.page_range_frame.grid(row=2, column=1, columnspan=2, padx=20, pady=(5, 15), sticky="ew")
        self.page_range_frame.grid_columnconfigure((0, 1), weight=1)

        self.start_page_var = tk.StringVar(value="1")
        self.start_page_entry = ctk.CTkEntry(
            self.page_range_frame,
            textvariable=self.start_page_var,
            width=80,
            placeholder_text="Start"
        )
        self.start_page_entry.grid(row=0, column=0, padx=(10, 5), pady=10)

        self.end_page_var = tk.StringVar()
        self.end_page_entry = ctk.CTkEntry(
            self.page_range_frame,
            textvariable=self.end_page_var,
            width=80,
            placeholder_text="End (optional)"
        )
        self.end_page_entry.grid(row=0, column=1, padx=(5, 10), pady=10)

    def create_control_frame(self):
        """Create control buttons frame"""
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        # Process button
        self.process_btn = ctk.CTkButton(
            self.control_frame,
            text="Start Extraction",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=40,
            command=self.start_extraction
        )
        self.process_btn.grid(row=0, column=0, padx=20, pady=15)

        # Stop button (initially disabled)
        self.stop_btn = ctk.CTkButton(
            self.control_frame,
            text="Stop",
            height=40,
            command=self.stop_extraction,
            state="disabled",
            fg_color="#D32F2F",
            hover_color="#B71C1C"
        )
        self.stop_btn.grid(row=0, column=1, padx=20, pady=15)

        # Clear log button
        self.clear_log_btn = ctk.CTkButton(
            self.control_frame,
            text="Clear Log",
            width=100,
            height=40,
            command=self.clear_log
        )
        self.clear_log_btn.grid(row=0, column=2, padx=20, pady=15)

        self.settings_btn = ctk.CTkButton(
            self.control_frame,
            text="Settings",
            width=100,
            height=40,
            command=self.open_settings
        )
        self.settings_btn.grid(row=0, column=3, padx=20, pady=15)

    def create_progress_frame(self):
        """Create progress display frame"""
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")
        self.progress_bar.set(0)

        # Progress label
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ready to process",
            font=ctk.CTkFont(size=12)
        )
        self.progress_label.grid(row=1, column=0, padx=20, pady=(0, 15))

    def create_log_frame(self):
        """Create log display frame"""
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=5, column=0, padx=20, pady=(10, 20), sticky="nsew")
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(0, weight=1)

        # Log title
        self.log_title = ctk.CTkLabel(
            self.log_frame,
            text="Processing Log",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.log_title.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="w")

        # Log text box
        self.log_text = ctk.CTkTextbox(
            self.log_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.log_text.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        # Make log text read-only initially
        self.log_text.configure(state="disabled")

    def browse_pdf_file(self):
        """Open file dialog to select PDF file"""
        file_path = filedialog.askopenfilename(
            title="Select PDF File",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if file_path:
            self.pdf_file_path.set(file_path)
            self.log_message(f"Selected PDF file: {Path(file_path).name}")

    def browse_output_dir(self):
        """Open directory dialog to select output directory"""
        dir_path = filedialog.askdirectory(
            title="Select Output Directory",
            initialdir=self.output_dir_path.get()
        )
        if dir_path:
            self.output_dir_path.set(dir_path)
            self.log_message(f"Selected output directory: {dir_path}")

    def open_settings(self):
        """Open the persistent application settings panel."""
        show_settings(self)

    @staticmethod
    def _load_saved_settings() -> dict:
        """Load saved settings, falling back to an empty configuration."""
        try:
            if config.SETTINGS_FILE.exists():
                with config.SETTINGS_FILE.open("r", encoding="utf-8") as settings_file:
                    settings = json.load(settings_file)
                return settings if isinstance(settings, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load saved settings: %s", exc)
        return {}

    def log_message(self, message: str):
        """
        Add a message to the log display

        Args:
            message (str): Message to log
        """
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.configure(state="disabled")
        self.log_text.see("end")  # Auto-scroll to bottom

    def update_progress(self, value: float, text: str = ""):
        """
        Update progress bar and label

        Args:
            value (float): Progress value between 0.0 and 1.0
            text (str): Optional status text
        """
        self.progress_bar.set(value)
        if text:
            self.progress_label.configure(text=text)
        self.update_idletasks()

    def start_extraction(self):
        """Start the PDF extraction process in a separate thread"""
        # Validate inputs
        if not self.validate_inputs():
            return

        # Disable UI during processing
        self.set_processing_state(True)
        self.stop_event.clear()
        self.processing_options = {
            "pdf_path": self.pdf_file_path.get().strip(),
            "output_dir": self.output_dir_path.get().strip(),
            "start_page": int(self.start_page_var.get()) if self.start_page_var.get().strip() else 1,
            "end_page": int(self.end_page_var.get()) if self.end_page_var.get().strip() else None,
            "save_intermediate": self.save_intermediate_var.get(),
            "open_output": self.open_output_var.get(),
        }

        # Clear log and reset progress
        self.clear_log()
        self.update_progress(0.0, "Starting extraction...")

        # Start processing thread
        self.processing_thread = threading.Thread(
            target=self.extraction_worker,
            daemon=True
        )
        self.processing_thread.start()

        logger.info("Started PDF extraction process")

    def validate_inputs(self) -> bool:
        """
        Validate user inputs before starting extraction

        Returns:
            bool: True if inputs are valid, False otherwise
        """
        # Check PDF file
        pdf_path = self.pdf_file_path.get().strip()
        if not pdf_path:
            messagebox.showerror("Validation Error", "Please select a PDF file.")
            return False

        is_valid, error_msg = validate_pdf_file(pdf_path)
        if not is_valid:
            messagebox.showerror("Validation Error", f"Invalid PDF file:\n{error_msg}")
            return False

        # Check output directory
        output_dir = self.output_dir_path.get().strip()
        if not output_dir:
            messagebox.showerror("Validation Error", "Please select an output directory.")
            return False

        # Validate page range if provided
        try:
            start_page = int(self.start_page_var.get()) if self.start_page_var.get().strip() else 1
            if start_page < 1:
                raise ValueError("Start page must be at least 1")

            end_page = int(self.end_page_var.get()) if self.end_page_var.get().strip() else None
            if end_page is not None and end_page < start_page:
                raise ValueError("End page must be greater than or equal to start page")
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid page range: {str(e)}")
            return False

        return True

    def set_processing_state(self, is_processing: bool):
        """
        Enable/disable UI elements based on processing state

        Args:
            is_processing (bool): True if processing, False otherwise
        """
        self.is_processing = is_processing

        # Update button states
        if is_processing:
            self.process_btn.configure(state="disabled", text="Processing...")
            self.stop_btn.configure(state="normal")
            self.pdf_browse_btn.configure(state="disabled")
            self.output_browse_btn.configure(state="disabled")
        else:
            self.process_btn.configure(state="normal", text="Start Extraction")
            self.stop_btn.configure(state="disabled")
            self.pdf_browse_btn.configure(state="normal")
            self.output_browse_btn.configure(state="normal")

    def stop_extraction(self):
        """Request stop of the extraction process"""
        if self.is_processing:
            self.log_message("Stop requested by user...")
            self.update_progress(0.0, "Stopping...")
            self.stop_event.set()

    def clear_log(self):
        """Clear the log display"""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.log_message("Log cleared.")

    def start_queue_processor(self):
        """Start processing messages from the worker thread"""
        self.process_queue()
        self.after(100, self.start_queue_processor)  # Check queue every 100ms

    def process_queue(self):
        """Process messages from the worker thread queue"""
        try:
            while True:  # Process all available messages
                message = self.message_queue.get_nowait()
                self.handle_worker_message(message)
        except queue.Empty:
            pass  # No messages waiting

    def handle_worker_message(self, message: dict):
        """
        Handle messages from the worker thread

        Args:
            message (dict): Message dictionary with 'type' and 'data' keys
        """
        msg_type = message.get("type")
        data = message.get("data")

        if msg_type == "log":
            self.log_message(data)
        elif msg_type == "progress":
            self.update_progress(data.get("value", 0), data.get("text", ""))
        elif msg_type == "complete":
            self.extraction_complete(data.get("success", False), data.get("message", ""))
        elif msg_type == "error":
            self.extraction_error(data)

    def extraction_worker(self):
        """Run the fixed-template SLD extraction in a background thread.

        Performance rule: the uploaded PDF is opened/extracted once, then all
        template rows search the in-memory page index. No equipment-schedule
        branch remains in the application.
        """
        try:
            options = self.processing_options
            pdf_path = options["pdf_path"]
            output_dir = options["output_dir"]
            start_page = options["start_page"]
            end_page = options["end_page"]
            save_intermediate = options["save_intermediate"]

            self.message_queue.put({"type": "log", "data": "Starting SLD template extraction..."})
            self.message_queue.put({"type": "log", "data": "Opening uploaded PTS PDF..."})
            pdf_processor = PDFProcessor(pdf_path)

            total_pages = pdf_processor.get_total_pages()
            actual_start = max(1, start_page)
            actual_end = min(total_pages, end_page) if end_page else total_pages
            if actual_start > total_pages:
                raise ValueError(
                    f"Start page {actual_start} is outside the PDF (it contains {total_pages} pages)"
                )
            if actual_end < actual_start:
                raise ValueError("End page must be greater than or equal to start page")

            project_root = Path(__file__).resolve().parent.parent
            template_path = project_root / "assets" / "Extracted Sheet Tempelate.xlsx"
            template = SLDTemplate(template_path)
            template_rows = template.load_rows()
            if not template_rows:
                raise ValueError("The SLD template contains no extractable rows in columns A-C.")

            self.message_queue.put({
                "type": "log",
                "data": (
                    f"Indexing physical PDF pages {actual_start}-{actual_end} once "
                    f"({actual_end - actual_start + 1} pages)..."
                )
            })

            intermediate_dir = None
            if save_intermediate:
                intermediate_dir = Path(output_dir) / "intermediate_text"

            def index_progress(done: int, total: int):
                # Indexing occupies the first 70% of progress.
                value = 0.70 * (done / max(total, 1))
                self.message_queue.put({
                    "type": "progress",
                    "data": {
                        "value": value,
                        "text": f"Indexing PDF: {done}/{total} physical pages"
                    }
                })

            pdf_index = PDFIndex.build(
                pdf_processor,
                start_page=actual_start,
                end_page=actual_end,
                progress_callback=index_progress,
                stop_callback=self.stop_event.is_set,
                intermediate_dir=intermediate_dir,
            )

            self.message_queue.put({
                "type": "log",
                "data": f"PDF indexed. Resolving {len(template_rows)} fixed template rows..."
            })

            extractor = SLDTemplateExtractor(pdf_index, pdf_path)
            project_name = extractor.extract_project_name()
            self.message_queue.put({
                "type": "log",
                "data": f"Project name: {project_name}"
            })

            def row_progress(done: int, total: int):
                value = 0.70 + 0.28 * (done / max(total, 1))
                self.message_queue.put({
                    "type": "progress",
                    "data": {
                        "value": value,
                        "text": f"Extracting template rows: {done}/{total}"
                    }
                })

            results = extractor.extract_rows(
                template_rows,
                progress_callback=row_progress,
                stop_callback=self.stop_event.is_set,
            )

            if self.stop_event.is_set():
                raise InterruptedError("Extraction cancelled by user.")

            ensure_directory(output_dir)
            output_path = Path(output_dir) / "Extracted Data.xlsx"
            self.message_queue.put({
                "type": "progress",
                "data": {"value": 0.99, "text": "Writing Excel output..."}
            })
            template.create_output(output_path, project_name, results)

            found = sum(1 for result in results.values() if result.value != "NA")
            missing = len(results) - found
            success_msg = (
                f"SLD extraction completed successfully!\n"
                f"Indexed {len(pdf_index.pages)} physical PDF pages once\n"
                f"Template rows: {len(results)} | Found: {found} | NA: {missing}\n"
                f"Saved to: {output_path}"
            )
            self.message_queue.put({
                "type": "complete",
                "data": {"success": True, "message": success_msg}
            })

            if options["open_output"]:
                try:
                    os.startfile(str(Path(output_dir)))
                except AttributeError:
                    if sys.platform == "darwin":
                        os.system(f'open "{output_dir}"')
                    else:
                        os.system(f'xdg-open "{output_dir}"')

        except InterruptedError:
            self.message_queue.put({
                "type": "complete",
                "data": {"success": False, "message": "Extraction cancelled by user."}
            })
        except Exception as e:
            error_msg = f"Error during extraction: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.message_queue.put({
                "type": "error",
                "data": {"message": error_msg, "exception": str(e)}
            })

    def extraction_complete(self, success: bool, message: str):
        """
        Handle extraction completion

        Args:
            success (bool): True if successful, False otherwise
            message (str): Completion message
        """
        self.set_processing_state(False)
        self.update_progress(1.0 if success else 0.0, "Complete" if success else "Failed")

        if success:
            self.log_message("✓ " + message)
            messagebox.showinfo("Extraction Complete", message)
        else:
            self.log_message("✗ Extraction failed: " + message)
            messagebox.showerror("Extraction Failed", message)

    def extraction_error(self, error_data: dict):
        """
        Handle extraction error

        Args:
            error_data (dict): Error information
        """
        self.set_processing_state(False)
        self.update_progress(0.0, "Error")

        error_msg = error_data.get("message", "Unknown error")
        self.log_message("✗ Error: " + error_msg)
        messagebox.showerror("Extraction Error", error_msg)


def main():
    """Main entry point for the application"""
    app = PDFExtractorApp()
    app.mainloop()


if __name__ == "__main__":
    main()