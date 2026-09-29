"""
Progress Dialog Module
Contains a progress dialog for long-running operations
"""

import customtkinter as ctk
import tkinter as tk
from pathlib import Path

class ProgressDialog(ctk.CTkToplevel):
    """
    A modal progress dialog for showing operation progress
    """

    def __init__(self, parent, title="Processing", message="Please wait..."):
        super().__init__(parent)

        self.title(title)
        self.geometry("400x150")
        self.resizable(False, False)

        # Make it modal
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        # Setup UI
        self.setup_ui(message)

        # Initialize progress
        self.progress_value = 0.0

    def setup_ui(self, message):
        """Setup the dialog UI components"""
        # Message label
        self.message_label = ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(size=12)
        )
        self.message_label.pack(pady=(20, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(self, width=300)
        self.progress_bar.pack(pady=10, padx=20, fill="x")
        self.progress_bar.set(0)

        # Percent label
        self.percent_label = ctk.CTkLabel(
            self,
            text="0%",
            font=ctk.CTkFont(size=10)
        )
        self.percent_label.pack(pady=(0, 15))

    def update_progress(self, value: float, message: str = None):
        """
        Update the progress bar

        Args:
            value (float): Progress value between 0.0 and 1.0
            message (str): Optional message to display
        """
        self.progress_value = value
        self.progress_bar.set(value)
        self.percent_label.configure(text=f"{int(value * 100)}%")

        if message:
            self.message_label.configure(text=message)

        self.update_idletasks()

    def set_message(self, message: str):
        """
        Update the message text

        Args:
            message (str): New message to display
        """
        self.message_label.configure(text=message)
        self.update_idletasks()

    def close_dialog(self):
        """Close the dialog"""
        self.grab_release()
        self.destroy()


def show_progress(parent, title="Processing", message="Please wait..."):
    """
    Convenience function to show a progress dialog

    Args:
        parent: Parent window
        title (str): Dialog title
        message (str): Initial message

    Returns:
        ProgressDialog: The dialog instance
    """
    dialog = ProgressDialog(parent, title, message)
    return dialog