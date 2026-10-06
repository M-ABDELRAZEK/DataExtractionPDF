"""Settings panel for the PTS-to-SLD extractor."""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import json
import logging
import config

logger = logging.getLogger(__name__)


class SettingsPanel(ctk.CTkToplevel):
    """Small settings dialog for the single SLD-template workflow."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("620x470")
        self.resizable(True, True)
        self.transient(parent)

        self.settings = self.load_default_settings()
        self.setup_ui()
        self.load_settings()

    def load_default_settings(self) -> dict:
        return {
            "general": {
                "theme": "System",
                "color_theme": "blue",
                "default_output_dir": str(Path.cwd() / "output"),
                "open_output_after": True,
                "log_level": "INFO",
            },
            "pdf_processing": {
                "save_intermediate": False,
            },
        }

    def setup_ui(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=20, pady=20, fill="both", expand=True)
        self.tabview.add("General")
        self.tabview.add("PDF Processing")
        self.setup_general_tab()
        self.setup_pdf_tab()

        buttons = ctk.CTkFrame(self)
        buttons.pack(padx=20, pady=(0, 20), fill="x")
        ctk.CTkButton(buttons, text="Reset to Defaults", command=self.reset_to_defaults).pack(
            side="left", padx=20, pady=10
        )
        ctk.CTkButton(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(10, 0), pady=10
        )
        ctk.CTkButton(buttons, text="Save Settings", command=self.save_settings).pack(
            side="right", padx=(10, 20), pady=10
        )

    def setup_general_tab(self):
        tab = self.tabview.tab("General")

        appearance = ctk.CTkFrame(tab)
        appearance.pack(padx=20, pady=20, fill="x")
        ctk.CTkLabel(appearance, text="Appearance", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        row = ctk.CTkFrame(appearance)
        row.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(row, text="Appearance Mode:").pack(side="left", padx=10, pady=10)
        self.theme_var = tk.StringVar(value="System")
        ctk.CTkOptionMenu(row, values=["System", "Light", "Dark"], variable=self.theme_var).pack(
            side="left", padx=5
        )

        row = ctk.CTkFrame(appearance)
        row.pack(fill="x", padx=15, pady=8)
        ctk.CTkLabel(row, text="Color Theme:").pack(side="left", padx=10, pady=10)
        self.color_theme_var = tk.StringVar(value="blue")
        ctk.CTkOptionMenu(row, values=["blue", "green", "dark-blue"], variable=self.color_theme_var).pack(
            side="left", padx=5
        )

        output = ctk.CTkFrame(tab)
        output.pack(padx=20, pady=10, fill="x")
        ctk.CTkLabel(output, text="Default Output Directory", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 8)
        )
        row = ctk.CTkFrame(output)
        row.pack(fill="x", padx=15, pady=(0, 12))
        self.output_dir_var = tk.StringVar()
        ctk.CTkEntry(row, textvariable=self.output_dir_var).pack(
            side="left", padx=(10, 5), pady=10, fill="x", expand=True
        )
        ctk.CTkButton(row, text="Browse", width=80, command=self.browse_output_dir).pack(
            side="right", padx=(5, 10), pady=10
        )

        options = ctk.CTkFrame(tab)
        options.pack(padx=20, pady=10, fill="x")
        self.open_output_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            options,
            text="Open output folder after extraction",
            variable=self.open_output_var,
        ).pack(anchor="w", padx=20, pady=(15, 10))

        row = ctk.CTkFrame(options)
        row.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkLabel(row, text="Log Level:").pack(side="left", padx=10, pady=10)
        self.log_level_var = tk.StringVar(value="INFO")
        ctk.CTkOptionMenu(
            row,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            variable=self.log_level_var,
        ).pack(side="left", padx=5)

    def setup_pdf_tab(self):
        tab = self.tabview.tab("PDF Processing")
        frame = ctk.CTkFrame(tab)
        frame.pack(padx=20, pady=20, fill="x")
        ctk.CTkLabel(frame, text="PDF Indexing", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=15, pady=(15, 8)
        )
        ctk.CTkLabel(
            frame,
            text=(
                "The uploaded PTS is read once and indexed in memory. Physical PDF page "
                "numbers (viewer pages 1..N) are used, so internal document page labels do not matter."
            ),
            justify="left",
            wraplength=520,
        ).pack(anchor="w", padx=15, pady=(0, 12))

        self.save_intermediate_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            frame,
            text="Save extracted page text for troubleshooting",
            variable=self.save_intermediate_var,
        ).pack(anchor="w", padx=20, pady=(0, 15))

    def browse_output_dir(self):
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.cwd()))
        if directory:
            self.output_dir_var.set(directory)

    def load_settings(self):
        path = Path(config.SETTINGS_FILE)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                for group, values in stored.items():
                    if group in self.settings and isinstance(values, dict):
                        self.settings[group].update(values)
            except Exception as exc:
                logger.warning("Could not load settings: %s", exc)

        general = self.settings["general"]
        pdf = self.settings["pdf_processing"]
        self.theme_var.set(general["theme"])
        self.color_theme_var.set(general["color_theme"])
        self.output_dir_var.set(general["default_output_dir"])
        self.open_output_var.set(bool(general["open_output_after"]))
        self.log_level_var.set(general["log_level"])
        self.save_intermediate_var.set(bool(pdf["save_intermediate"]))

    def save_settings(self):
        settings = {
            "general": {
                "theme": self.theme_var.get(),
                "color_theme": self.color_theme_var.get(),
                "default_output_dir": self.output_dir_var.get(),
                "open_output_after": bool(self.open_output_var.get()),
                "log_level": self.log_level_var.get(),
            },
            "pdf_processing": {
                "save_intermediate": bool(self.save_intermediate_var.get()),
            },
        }
        try:
            path = Path(config.SETTINGS_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
            ctk.set_appearance_mode(settings["general"]["theme"])
            messagebox.showinfo("Settings", "Settings saved.")
            self.destroy()
        except Exception as exc:
            logger.exception("Failed to save settings")
            messagebox.showerror("Settings", f"Failed to save settings:\n{exc}")

    def reset_to_defaults(self):
        self.settings = self.load_default_settings()
        general = self.settings["general"]
        pdf = self.settings["pdf_processing"]
        self.theme_var.set(general["theme"])
        self.color_theme_var.set(general["color_theme"])
        self.output_dir_var.set(general["default_output_dir"])
        self.open_output_var.set(general["open_output_after"])
        self.log_level_var.set(general["log_level"])
        self.save_intermediate_var.set(pdf["save_intermediate"])



def show_settings(parent):
    """Open the settings dialog for the main application window."""
    dialog = SettingsPanel(parent)
    dialog.grab_set()
    return dialog
