"""
Main Window Module
Contains the main application window and GUI components
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import threading
import queue
import json
import logging
from datetime import datetime
from pathlib import Path
import sys
import os

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from core.pipeline import run_pipeline
from core.groq_extractor import GroqExtractor, DEFAULT_MODEL, resolve_api_key
from cad.gis_planner import build_cad_plan_from_json
from cad.autocad_backend import insert_draft
from cad.bay_layout import refresh_bay_layout
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
        self.title("PTS -> Markdown Sections -> Groq AI -> GIS CAD (v6)")
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
        self.last_cad_plan = None

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
            text="PDF -> Section Markdown -> Groq AI -> JSON -> Excel",
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

        self.use_ai_var = tk.BooleanVar(value=True)
        self.groq_cb = ctk.CTkCheckBox(self.options_frame,
            text="Use Groq Cloud API for extraction (GROQ_API_KEY)", variable=self.use_ai_var)
        self.groq_cb.grid(row=3, column=0, columnspan=2, padx=20, pady=10, sticky="w")
        self.cad_plan_var = tk.BooleanVar(value=True)
        self.cad_plan_cb = ctk.CTkCheckBox(self.options_frame,
            text="Prepare GIS CAD plan from AI JSON", variable=self.cad_plan_var)
        self.cad_plan_cb.grid(row=3, column=2, padx=20, pady=10, sticky="w")
        self.ocr_var = tk.BooleanVar(value=False)
        self.ocr_cb = ctk.CTkCheckBox(self.options_frame,
            text="OCR image-only pages (slow/local)", variable=self.ocr_var)
        self.ocr_cb.grid(row=5, column=0, columnspan=2, padx=20, pady=(4,12), sticky="w")
        self.ai_budget_label = ctk.CTkLabel(self.options_frame,
            text="Test limit: Max AI rows (blank = ALL 174):")
        self.ai_budget_label.grid(row=4, column=0, padx=20, pady=(4,12), sticky="w")
        self.ai_budget_var = tk.StringVar(value="")
        self.ai_budget_entry = ctk.CTkEntry(self.options_frame,
            textvariable=self.ai_budget_var, width=90)
        self.ai_budget_entry.grid(row=4, column=1, padx=20, pady=(4,12), sticky="w")
        # V3 regression fix: the submit code previously referenced two widgets
        # which had never been created, crashing before the Groq call.
        self.groq_key_label = ctk.CTkLabel(self.options_frame,
            text="Groq API key (hidden; not saved):")
        self.groq_key_label.grid(row=6, column=0, padx=20, pady=(4,10), sticky="w")
        self.groq_key_entry = ctk.CTkEntry(self.options_frame,
            placeholder_text="Or use GROQ_API_KEY environment variable",
            show="*", width=300)
        self.groq_key_entry.grid(row=6, column=1, columnspan=2,
                                 padx=20, pady=(4,10), sticky="ew")
        self.groq_model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.groq_model_label = ctk.CTkLabel(self.options_frame,text='Groq model:')
        self.groq_model_label.grid(row=8,column=0,padx=20,pady=(3,8),sticky='w')
        self.groq_model_dropdown = ctk.CTkOptionMenu(self.options_frame,
            values=['openai/gpt-oss-20b','llama-3.3-70b-versatile','llama-3.1-8b-instant','mixtral-8x7b-32768','openai/gpt-oss-120b','qwen/qwen3.8-27b'],
            variable=self.groq_model_var)
        self.groq_model_dropdown.grid(row=8,column=1,columnspan=2,padx=20,pady=(3,8),sticky='ew')
        self.cad_vendor_var = tk.StringVar(value="HYUNDAI")
        self.cad_vendor_label = ctk.CTkLabel(self.options_frame,
            text="CAD symbol vendor:")
        self.cad_vendor_label.grid(row=7, column=0, padx=20, pady=(4,12), sticky="w")
        self.cad_vendor_dropdown = ctk.CTkOptionMenu(self.options_frame,
            values=["HYUNDAI"], variable=self.cad_vendor_var)
        self.cad_vendor_dropdown.grid(row=7, column=1, padx=20, pady=(4,12), sticky="w")
        self.test_groq_btn = ctk.CTkButton(self.options_frame,
            text="Test Groq Connection", command=self.test_groq_connection)
        self.test_groq_btn.grid(row=7, column=2, padx=20, pady=(4,12), sticky="w")

    def test_groq_connection(self):
        """User-triggered CLOUD test (uses a few tokens, never logs the key)."""
        key, key_source = resolve_api_key(self.groq_key_entry.get())
        if not key:
            messagebox.showwarning('Groq API',
                'Enter a NEW Groq API key in the hidden field, or set GROQ_API_KEY.')
            return
        model = self.groq_model_var.get()  # read Tk state on the GUI thread
        self.test_groq_btn.configure(state='disabled',text='Testing Groq...')
        def worker():
            try:
                result=GroqExtractor(model=model,api_key=key,timeout_seconds=20).test_connection()
                message=(f'Groq cloud connection OK. Model: {result["model"]}; '
                         f'key source: {key_source}; transport: {result["transport"]}')
            except Exception as exc:
                message=f'Groq connection failed: {type(exc).__name__}: {str(exc)[:650]}'
            self.message_queue.put({'type':'groq_test_result','data':message})
        threading.Thread(target=worker,daemon=True).start()

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

        self.cad_btn = ctk.CTkButton(self.control_frame, text="Assemble CAD Draft",
            command=self.draw_cad_draft, state="disabled", width=180)
        self.cad_btn.grid(row=1, column=0, columnspan=2, padx=20, pady=(0,12), sticky="w")

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
        saved = self._load_saved_settings()
        general = saved.get("general", {})
        pdf = saved.get("pdf_processing", {})
        if "default_output_dir" in general:
            self.output_dir_path.set(general["default_output_dir"])
        if "open_output_after" in general:
            self.open_output_var.set(bool(general["open_output_after"]))
        if "save_intermediate" in pdf:
            self.save_intermediate_var.set(bool(pdf["save_intermediate"]))

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
            "use_ai": self.use_ai_var.get(),
            "groq_api_key": self.groq_key_entry.get().strip() or None,
            "groq_model": self.groq_model_var.get(),
            "max_ai_rows": int(self.ai_budget_var.get()) if self.ai_budget_var.get().strip() else None,
            "cad_plan": self.cad_plan_var.get(),
            "cad_vendor": self.cad_vendor_var.get(),
            "ocr_missing": self.ocr_var.get(),
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

        # Validate page range and optional AI budget if provided
        try:
            if self.ai_budget_var.get().strip() and int(self.ai_budget_var.get()) < 0:
                raise ValueError("Max Groq rows must be non-negative")
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
            self.cad_btn.configure(state="disabled")
        else:
            self.process_btn.configure(state="normal", text="Start Extraction")
            self.stop_btn.configure(state="disabled")
            self.pdf_browse_btn.configure(state="normal")
            self.output_browse_btn.configure(state="normal")
            self.cad_btn.configure(state="normal" if self.last_cad_plan else "disabled")

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
        elif msg_type == 'groq_test_result':
            self.log_message(data)
            self.test_groq_btn.configure(state='normal',text='Test Groq Connection')
        elif msg_type == "progress":
            self.update_progress(data.get("value", 0), data.get("text", ""))
        elif msg_type == "complete":
            self.extraction_complete(data.get("success", False), data.get("message", ""))
        elif msg_type == "error":
            self.extraction_error(data)
        elif msg_type == "cad_complete":
            self.cad_btn.configure(state="normal", text="Assemble CAD Draft")
            messagebox.showinfo("CAD Draft Ready",
                f"AutoCAD component draft created and saved to:\n{data}\n\n"
                "Note: This is an unconnected layout draft, not an approved electrical SLD.")
        elif msg_type == "cad_error":
            self.cad_btn.configure(state="normal", text="Assemble CAD Draft")
            error_msg = data.get("message", "Unknown error") if isinstance(data, dict) else str(data)
            self.log_message("✗ " + error_msg)
            messagebox.showerror("CAD Error", error_msg)

    def extraction_worker(self):
        """Section-aware extraction with optional, strictly localized Groq calls."""
        try:
            options = self.processing_options
            if options['use_ai'] and not resolve_api_key(options['groq_api_key'])[0]:
                raise ValueError('Enter the Groq API key in the GUI or configure .env locally' )
            def report(value, label):
                self.message_queue.put({'type':'progress',
                    'data':{'value':value,'text':label}})
            self.message_queue.put({'type':'log','data':'Extracting auditable Markdown sections ...'})
            root = Path(__file__).resolve().parent.parent
            result = run_pipeline(options['pdf_path'], options['output_dir'],
                root/'assets'/'Extracted Sheet Tempelate.xlsx',
                start_page=options['start_page'], end_page=options['end_page'],
                use_ai=options['use_ai'], groq_api_key=options['groq_api_key'],
                groq_model=options['groq_model'],
                max_ai_rows=options['max_ai_rows'],
                ocr_missing=options['ocr_missing'],
                progress=report, stop=self.stop_event.is_set)
            self.last_cad_plan = None
            if options['cad_plan']:
                plan_file = Path(options['output_dir'])/'gis_plan.json'
                plan = build_cad_plan_from_json(result['results_json'],
                    root/'assets/cad/VERTICES.xlsx',
                    root/'assets/cad/vendors'/options['cad_vendor'], plan_file,
                    vendor=options['cad_vendor'])
                self.last_cad_plan = str(plan_file)
                self.message_queue.put({'type':'log',
                    'data':f'GIS drawing plan created ({len(plan["issues"])} review items). Drawing is not electrically connected.'})
            success = (
                f'Extraction completed. Pages: {result["pdf_pages"]}; '
                f'Markdown sections: {result["markdown_sections"]}; '
                f'Resolved rows: {result["found"]}/{result["total_rows"]}; Groq batches: {result["ai_requested"]}\n'
                f'Excel: {result["output_excel"]}\n'
                f'QA: {result["audit_json"]}\n'
                f'Extraction JSON: {result["results_json"]}\n'
                f'CAD plan: {self.last_cad_plan or "not requested"}')
            self.message_queue.put({'type':'complete',
                'data':{'success':True,'message':success}})
            if options['open_output'] and os.name == 'nt':
                os.startfile(str(Path(options['output_dir'])))
        except InterruptedError:
            self.message_queue.put({'type':'complete',
                'data':{'success':False,'message':'Stopped by user'}})
        except Exception as exc:
            logger.exception('Pipeline failed')
            self.message_queue.put({'type':'error',
                'data':{'message':str(exc),'exception':str(exc)}})

    def draw_cad_draft(self):
        """User-initiated CAD draft; unresolved BOM entries block unsafe output."""
        if not self.last_cad_plan:
            messagebox.showwarning('CAD', 'Run extraction and prepare GIS plan first.')
            return
        source = Path(self.last_cad_plan)
        plan_data = json.loads(source.read_text(encoding='utf-8'))
        # Future bays are DISTINCT from equipped spares, and can always be
        # explicitly added/changed by the user regardless of source value.
        future_data = plan_data['components'].get('F-INCOMER', {})
        future_detected = future_data.get('quantity')
        future_default = future_detected if future_detected is not None else 0
        future_answer = simpledialog.askinteger('Future GIS incomers',
            'Future bays to show on CAD?\n'
            f'AI-backed specification count: {future_detected if future_detected is not None else "not established"}.\n'
            'Enter 0 if none; equipped spares are NOT future bays.',
            initialvalue=future_default, minvalue=0, maxvalue=200, parent=self)
        if future_answer is None: return
        approved = {}
        if future_detected != future_answer or future_detected is None:
            approved['F-INCOMER'] = future_answer
            future_data['quantity'] = future_answer
            plan_data['future_bays'] = {'drawing_quantity':future_answer,
                'source':'USER_OVERRIDE','manual_override':future_answer}
        for name, data in plan_data['components'].items():
            if data['quantity'] is None:
                quantity = simpledialog.askinteger('Confirm GIS quantity',
                    f'Unresolved {name} quantity. Enter a verified number for CAD draft:',
                    minvalue=0, maxvalue=200, parent=self)
                if quantity is None:
                    self.log_message(f'CAD drawing cancelled: {name} quantity not confirmed')
                    return
                data['quantity'] = quantity
                approved[name] = quantity
        refresh_bay_layout(plan_data)
        if approved:
            source = source.with_name('gis_plan_manual_draft.json')
            plan_data['manual_quantity_overrides'] = approved
            source.write_text(json.dumps(plan_data, indent=2), encoding='utf-8')
        else:
            # Keep the reviewed geometry synchronized with displayed counts.
            source = source.with_name('gis_plan_reviewed_draft.json')
            source.write_text(json.dumps(plan_data, indent=2), encoding='utf-8')
        layout=plan_data.get('bay_layout',{})
        remote_summary='; '.join(e.get('name','') for e in layout.get('remote_ends',[]))
        split=f"GIS bay slots: LEFT {layout.get('total_on_left',0)} | RIGHT {layout.get('total_on_right',0)}\n"
        if not messagebox.askokcancel('Draft only',
               split + f'Remote ends: {remote_summary or "not found"}\n\n' +
               'This creates an UNCONNECTED layout of CAD symbols. '
               'It is NOT a checked electrical SLD. Continue?', parent=self):
            return
        template = Path(__file__).resolve().parent.parent/'assets/cad/SLD Drawing Template 0.1.dwt'
        filename = source.parent / f'GIS_DRAFT_UNCONNECTED_{datetime.now():%Y%m%d_%H%M%S}.dwg'
        self.cad_btn.configure(state="disabled", text="Drafting CAD...")
        def worker():
            try:
                result = insert_draft(source, template, filename,
                                      on_progress=lambda text: self.message_queue.put({'type':'log', 'data':text}))
                self.message_queue.put({'type':'log','data':f'AutoCAD component draft saved: {result}'})
                self.message_queue.put({'type':'cad_complete','data':str(result)})
            except Exception as exc:
                self.message_queue.put({'type':'cad_error',
                    'data':{'message':f'CAD drawing failed: {exc}'}})
        threading.Thread(target=worker, daemon=True).start()

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