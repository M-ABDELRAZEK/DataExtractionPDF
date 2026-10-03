"""
Settings Panel Module
Contains advanced settings and configuration options
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import json
import logging
import config

logger = logging.getLogger(__name__)

class SettingsPanel(ctk.CTkToplevel):
    """
    Advanced settings panel for configuring the PDF extractor
    """

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Settings")
        self.geometry("600x500")
        self.resizable(True, True)

        # Make it transient but not necessarily modal
        self.transient(parent)

        # Settings storage
        self.settings = self.load_default_settings()

        # Setup UI
        self.setup_ui()
        self.load_settings()

        logger.info("Settings panel initialized")

    def load_default_settings(self) -> dict:
        """Load default settings"""
        return {
            "general": {
                "theme": "System",
                "color_theme": "blue",
                "default_output_dir": str(Path.cwd() / "output"),
                "open_output_after": True,
                "log_level": "INFO"
            },
            "pdf_processing": {
                "extract_tables": False,
                "save_intermediate": False,
                "batch_size": 100,
                "timeout_seconds": 300
            },
            "extraction": {
                "min_confidence": 0.3,
                "max_pages_per_batch": 50,
                "enable_context_scoring": True,
                "enable_proximity_scoring": True
            },
            "excel_output": {
                "auto_filter": True,
                "freeze_header": True,
                "confidence_coloring": True,
                "summary_sheet": True
            }
        }

    def setup_ui(self):
        """Setup the settings UI"""
        # Create tabview
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=20, fill="both", expand=True)

        # Add tabs
        self.tabview.add("General")
        self.tabview.add("PDF Processing")
        self.tabview.add("Extraction Rules")
        self.tabview.add("Excel Output")

        # Setup each tab
        self.setup_general_tab()
        self.setup_pdf_tab()
        self.setup_extraction_tab()
        self.setup_excel_tab()

        # Buttons frame
        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.pack(padx=20, pady=(0, 20), fill="x")

        self.save_btn = ctk.CTkButton(
            self.button_frame,
            text="Save Settings",
            command=self.save_settings
        )
        self.save_btn.pack(side="right", padx=(10, 20), pady=10)

        self.cancel_btn = ctk.CTkButton(
            self.button_frame,
            text="Cancel",
            command=self.destroy
        )
        self.cancel_btn.pack(side="right", padx=(10, 0), pady=10)

        self.reset_btn = ctk.CTkButton(
            self.button_frame,
            text="Reset to Defaults",
            command=self.reset_to_defaults
        )
        self.reset_btn.pack(side="left", padx=20, pady=10)

    def setup_general_tab(self):
        """Setup general settings tab"""
        tab = self.tabview.tab("General")

        # Appearance settings
        appearance_frame = ctk.CTkFrame(tab)
        appearance_frame.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(appearance_frame, text="Appearance", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        # Theme selection
        theme_frame = ctk.CTkFrame(appearance_frame)
        theme_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(theme_frame, text="Appearance Mode:").pack(side="left", padx=(10, 5), pady=10)
        self.theme_var = tk.StringVar(value=self.settings["general"]["theme"])
        theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["System", "Light", "Dark"],
            variable=self.theme_var
        )
        theme_menu.pack(side="left", padx=5, pady=10)

        # Color theme
        color_frame = ctk.CTkFrame(appearance_frame)
        color_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(color_frame, text="Color Theme:").pack(side="left", padx=(10, 5), pady=10)
        self.color_theme_var = tk.StringVar(value=self.settings["general"]["color_theme"])
        color_menu = ctk.CTkOptionMenu(
            color_frame,
            values=["blue", "green", "dark-blue"],
            variable=self.color_theme_var
        )
        color_menu.pack(side="left", padx=5, pady=10)

        # Default output directory
        output_frame = ctk.CTkFrame(tab)
        output_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(output_frame, text="Default Output Directory:", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        dir_frame = ctk.CTkFrame(output_frame)
        dir_frame.pack(fill="x", padx=15, pady=(0, 15))

        self.output_dir_var = tk.StringVar(value=self.settings["general"]["default_output_dir"])
        output_entry = ctk.CTkEntry(
            dir_frame,
            textvariable=self.output_dir_var,
            width=300
        )
        output_entry.pack(side="left", padx=(10, 5), pady=10, fill="x", expand=True)

        output_browse_btn = ctk.CTkButton(
            dir_frame,
            text="Browse",
            width=80,
            command=self.browse_output_dir
        )
        output_browse_btn.pack(side="right", padx=(5, 10), pady=10)

        # Other options
        options_frame = ctk.CTkFrame(tab)
        options_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(options_frame, text="Other Options", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        self.open_output_var = tk.BooleanVar(value=self.settings["general"]["open_output_after"])
        ctk.CTkCheckBox(
            options_frame,
            text="Open output folder after extraction",
            variable=self.open_output_var
        ).pack(anchor="w", padx=20, pady=10)

        # Log level
        log_frame = ctk.CTkFrame(options_frame)
        log_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(log_frame, text="Log Level:").pack(side="left", padx=(10, 5), pady=10)
        self.log_level_var = tk.StringVar(value=self.settings["general"]["log_level"])
        log_menu = ctk.CTkOptionMenu(
            log_frame,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            variable=self.log_level_var
        )
        log_menu.pack(side="left", padx=5, pady=10)

    def setup_pdf_tab(self):
        """Setup PDF processing settings tab"""
        tab = self.tabview.tab("PDF Processing")

        # Processing options
        proc_frame = ctk.CTkFrame(tab)
        proc_frame.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(proc_frame, text="Processing Options", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        self.extract_tables_var = tk.BooleanVar(value=self.settings["pdf_processing"]["extract_tables"])
        ctk.CTkCheckBox(
            proc_frame,
            text="Extract tables from PDF (experimental)",
            variable=self.extract_tables_var
        ).pack(anchor="w", padx=20, pady=10)

        self.save_intermediate_var = tk.BooleanVar(value=self.settings["pdf_processing"]["save_intermediate"])
        ctk.CTkCheckBox(
            proc_frame,
            text="Save intermediate text files for debugging",
            variable=self.save_intermediate_var
        ).pack(anchor="w", padx=20, pady=10)

        # Batch size
        batch_frame = ctk.CTkFrame(proc_frame)
        batch_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(batch_frame, text="Pages per batch:").pack(side="left", padx=(10, 5), pady=10)
        self.batch_size_var = tk.StringVar(value=str(self.settings["pdf_processing"]["batch_size"]))
        batch_entry = ctk.CTkEntry(
            batch_frame,
            textvariable=self.batch_size_var,
            width=80
        )
        batch_entry.pack(side="left", padx=5, pady=10)

        # Timeout
        timeout_frame = ctk.CTkFrame(proc_frame)
        timeout_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(timeout_frame, text="Processing timeout (seconds):").pack(side="left", padx=(10, 5), pady=10)
        self.timeout_var = tk.StringVar(value=str(self.settings["pdf_processing"]["timeout_seconds"]))
        timeout_entry = ctk.CTkEntry(
            timeout_frame,
            textvariable=self.timeout_var,
            width=80
        )
        timeout_entry.pack(side="left", padx=5, pady=10)

    def setup_extraction_tab(self):
        """Setup extraction rules settings tab"""
        tab = self.tabview.tab("Extraction Rules")

        # Confidence settings
        conf_frame = ctk.CTkFrame(tab)
        conf_frame.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(conf_frame, text="Confidence Settings", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        # Minimum confidence
        min_conf_frame = ctk.CTkFrame(conf_frame)
        min_conf_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(min_conf_frame, text="Minimum confidence threshold:").pack(side="left", padx=(10, 5), pady=10)
        self.min_confidence_var = tk.StringVar(value=str(self.settings["extraction"]["min_confidence"]))
        min_conf_entry = ctk.CTkEntry(
            min_conf_frame,
            textvariable=self.min_confidence_var,
            width=80
        )
        min_conf_entry.pack(side="left", padx=5, pady=10)
        ctk.CTkLabel(min_conf_frame, text="(0.0 - 1.0)").pack(side="left", padx=5, pady=10)

        # Scoring options
        scoring_frame = ctk.CTkFrame(conf_frame)
        scoring_frame.pack(fill="x", padx=15, pady=10)

        self.enable_context_var = tk.BooleanVar(value=self.settings["extraction"]["enable_context_scoring"])
        ctk.CTkCheckBox(
            scoring_frame,
            text="Enable context-based scoring",
            variable=self.enable_context_var
        ).pack(anchor="w", padx=20, pady=8)

        self.enable_proximity_var = tk.BooleanVar(value=self.settings["extraction"]["enable_proximity_scoring"])
        ctk.CTkCheckBox(
            scoring_frame,
            text="Enable proximity-based scoring",
            variable=self.enable_proximity_var
        ).pack(anchor="w", padx=20, pady=8)

        # Batch processing
        batch_frame = ctk.CTkFrame(conf_frame)
        batch_frame.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(batch_frame, text="Max pages per batch:").pack(side="left", padx=(10, 5), pady=10)
        self.max_pages_var = tk.StringVar(value=str(self.settings["extraction"]["max_pages_per_batch"]))
        max_pages_entry = ctk.CTkEntry(
            batch_frame,
            textvariable=self.max_pages_var,
            width=80
        )
        max_pages_entry.pack(side="left", padx=5, pady=10)

    def setup_excel_tab(self):
        """Setup Excel output settings tab"""
        tab = self.tabview.tab("Excel Output")

        # Output options
        output_frame = ctk.CTkFrame(tab)
        output_frame.pack(padx=20, pady=20, fill="x")

        ctk.CTkLabel(output_frame, text="Excel Output Options", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        self.auto_filter_var = tk.BooleanVar(value=self.settings["excel_output"]["auto_filter"])
        ctk.CTkCheckBox(
            output_frame,
            text="Enable auto-filter on data columns",
            variable=self.auto_filter_var
        ).pack(anchor="w", padx=20, pady=10)

        self.freeze_header_var = tk.BooleanVar(value=self.settings["excel_output"]["freeze_header"])
        ctk.CTkCheckBox(
            output_frame,
            text="Freeze header row",
            variable=self.freeze_header_var
        ).pack(anchor="w", padx=20, pady=10)

        self.confidence_coloring_var = tk.BooleanVar(value=self.settings["excel_output"]["confidence_coloring"])
        ctk.CTkCheckBox(
            output_frame,
            text="Color-code rows by confidence level",
            variable=self.confidence_coloring_var
        ).pack(anchor="w", padx=20, pady=10)

        self.summary_sheet_var = tk.BooleanVar(value=self.settings["excel_output"]["summary_sheet"])
        ctk.CTkCheckBox(
            output_frame,
            text="Include summary statistics sheet",
            variable=self.summary_sheet_var
        ).pack(anchor="w", padx=20, pady=10)

    def browse_output_dir(self):
        """Open directory browser for output directory"""
        from tkinter import filedialog
        directory = filedialog.askdirectory(
            title="Select Default Output Directory",
            initialdir=self.output_dir_var.get()
        )
        if directory:
            self.output_dir_var.set(directory)

    def load_settings(self):
        """Load persisted settings and reflect them in the controls."""
        try:
            if config.SETTINGS_FILE.exists():
                with config.SETTINGS_FILE.open("r", encoding="utf-8") as settings_file:
                    saved = json.load(settings_file)
                if isinstance(saved, dict):
                    for section, values in saved.items():
                        if isinstance(values, dict):
                            self.settings.setdefault(section, {}).update(values)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load settings file: %s", exc)

        self.theme_var.set(self.settings["general"]["theme"])
        self.color_theme_var.set(self.settings["general"]["color_theme"])
        self.output_dir_var.set(self.settings["general"]["default_output_dir"])
        self.open_output_var.set(self.settings["general"]["open_output_after"])
        self.log_level_var.set(self.settings["general"]["log_level"])
        self.extract_tables_var.set(self.settings["pdf_processing"]["extract_tables"])
        self.save_intermediate_var.set(self.settings["pdf_processing"]["save_intermediate"])
        self.batch_size_var.set(str(self.settings["pdf_processing"]["batch_size"]))
        self.timeout_var.set(str(self.settings["pdf_processing"]["timeout_seconds"]))
        self.min_confidence_var.set(str(self.settings["extraction"]["min_confidence"]))
        self.enable_context_var.set(self.settings["extraction"]["enable_context_scoring"])
        self.enable_proximity_var.set(self.settings["extraction"]["enable_proximity_scoring"])
        self.max_pages_var.set(str(self.settings["extraction"]["max_pages_per_batch"]))
        self.auto_filter_var.set(self.settings["excel_output"]["auto_filter"])
        self.freeze_header_var.set(self.settings["excel_output"]["freeze_header"])
        self.confidence_coloring_var.set(self.settings["excel_output"]["confidence_coloring"])
        self.summary_sheet_var.set(self.settings["excel_output"]["summary_sheet"])

    def save_settings(self):
        """Save current settings"""
        try:
            # Update settings from UI
            self.settings["general"]["theme"] = self.theme_var.get()
            self.settings["general"]["color_theme"] = self.color_theme_var.get()
            self.settings["general"]["default_output_dir"] = self.output_dir_var.get()
            self.settings["general"]["open_output_after"] = self.open_output_var.get()
            self.settings["general"]["log_level"] = self.log_level_var.get()

            self.settings["pdf_processing"]["extract_tables"] = self.extract_tables_var.get()
            self.settings["pdf_processing"]["save_intermediate"] = self.save_intermediate_var.get()
            self.settings["pdf_processing"]["batch_size"] = int(self.batch_size_var.get())
            self.settings["pdf_processing"]["timeout_seconds"] = int(self.timeout_var.get())

            self.settings["extraction"]["min_confidence"] = float(self.min_confidence_var.get())
            self.settings["extraction"]["enable_context_scoring"] = self.enable_context_var.get()
            self.settings["extraction"]["enable_proximity_scoring"] = self.enable_proximity_var.get()
            self.settings["extraction"]["max_pages_per_batch"] = int(self.max_pages_var.get())

            self.settings["excel_output"]["auto_filter"] = self.auto_filter_var.get()
            self.settings["excel_output"]["freeze_header"] = self.freeze_header_var.get()
            self.settings["excel_output"]["confidence_coloring"] = self.confidence_coloring_var.get()
            self.settings["excel_output"]["summary_sheet"] = self.summary_sheet_var.get()

            with config.SETTINGS_FILE.open("w", encoding="utf-8") as settings_file:
                json.dump(self.settings, settings_file, indent=2)

            logger.info("Settings saved successfully")

            # Apply theme changes immediately if needed
            # self.apply_theme_changes()

            # Show confirmation
            from tkinter import messagebox
            messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")
            self.destroy()

        except ValueError as e:
            from tkinter import messagebox
            messagebox.showerror("Invalid Input", f"Please check your settings: {str(e)}")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")

    def reset_to_defaults(self):
        """Reset settings to defaults"""
        from tkinter import messagebox
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset all settings to default values?"):
            self.settings = self.load_default_settings()
            self.load_settings()  # Reload UI from settings
            logger.info("Settings reset to defaults")

    def apply_theme_changes(self):
        """Apply theme changes immediately"""
        try:
            ctk.set_appearance_mode(self.theme_var.get())
            ctk.set_default_color_theme(self.color_theme_var.get())
            logger.info(f"Applied theme: {self.theme_var.get()}, color theme: {self.color_theme_var.get()}")
        except Exception as e:
            logger.error(f"Error applying theme changes: {e}")


def show_settings(parent):
    """
    Convenience function to show the settings panel

    Args:
        parent: Parent window

    Returns:
        SettingsPanel: The settings panel instance
    """
    panel = SettingsPanel(parent)
    return panel