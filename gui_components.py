import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from config import GUIConfig, RateLimits
from utils import get_timestamp

class OptionsWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Options")
        self.window.geometry(f"{GUIConfig.OPTIONS_SIZE[0]}x{GUIConfig.OPTIONS_SIZE[1]}")
        self.window.transient(parent)
        self.window.grab_set()

        content_frame = ttk.Frame(self.window, padding=GUIConfig.PADDING)
        content_frame.pack(anchor="nw")

        bold_font = ("TkDefaultFont", 10, "bold")
        
        ttk.Label(content_frame, text="Search Options:", font=bold_font).pack(anchor="w", pady=(0, GUIConfig.PADY))
        self.verified_var = tk.BooleanVar(value=self.app.verified_only.get())
        ttk.Checkbutton(content_frame, text="Search only for verified accounts", variable=self.verified_var).pack(anchor="w")
        self.no_replies_var = tk.BooleanVar(value=self.app.no_replies.get())
        ttk.Checkbutton(content_frame, text="Exclude replies in search", variable=self.no_replies_var).pack(anchor="w")

        ttk.Label(content_frame, text="API License Level:", font=bold_font).pack(anchor="w", pady=(GUIConfig.PADY * 2, GUIConfig.PADY))
        self.license_var = tk.StringVar(value=self.app.license_level.get())
        ttk.Combobox(content_frame, textvariable=self.license_var, values=list(RateLimits.LIMITS.keys()), state="readonly").pack(anchor="w")

        ttk.Label(content_frame, text="Fallback Retry Interval:", font=bold_font).pack(anchor="w", pady=(GUIConfig.PADY * 2, GUIConfig.PADY))
        self.retry_interval_var = tk.StringVar(value=str(self.app.retry_interval // 60))
        ttk.Combobox(content_frame, textvariable=self.retry_interval_var, values=["5", "15", "30", "60"], state="readonly").pack(anchor="w")
        ttk.Label(content_frame, text="(in minutes)").pack(anchor="w")

        ttk.Label(content_frame, text="Debug Options:", font=bold_font).pack(anchor="w", pady=(GUIConfig.PADY * 2, GUIConfig.PADY))
        self.debug_var = tk.BooleanVar(value=self.app.debug_mode.get())
        ttk.Checkbutton(content_frame, text="Enable debug logging", variable=self.debug_var).pack(anchor="w")

        ttk.Button(content_frame, text="Close", command=self.window.destroy).pack(anchor="w", pady=GUIConfig.PADY * 2)

class StatusWindow:
    def __init__(self, parent, x: int, y: int):
        self.window = tk.Toplevel(parent)
        self.window.title("Status Log")
        self.window.geometry(f"{GUIConfig.STATUS_SIZE[0]}x{GUIConfig.STATUS_SIZE[1]}+{x}+{y}")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.text = ScrolledText(self.window, height=20, width=80, wrap=tk.WORD)
        self.text.pack(fill="both", expand=True, padx=GUIConfig.PADDING, pady=GUIConfig.PADDING)
        self.text.config(state="disabled")

    def update(self, message: str):
        self.text.config(state="normal")
        self.text.insert(tk.END, f"[{get_timestamp()}] {message}\n")
        self.text.see(tk.END)
        self.text.config(state="disabled")

    def on_close(self):
        self.window.withdraw()