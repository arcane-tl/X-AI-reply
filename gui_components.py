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

        ttk.Label(content_frame, text="Max Search Results:", font=bold_font).pack(anchor="w", pady=(GUIConfig.PADY * 2, GUIConfig.PADY))
        self.max_results_var = tk.StringVar(value=str(self.app.max_search_results))
        ttk.Entry(content_frame, textvariable=self.max_results_var, width=10).pack(anchor="w")

        ttk.Label(content_frame, text="Retry Times:", font=bold_font).pack(anchor="w", pady=(GUIConfig.PADY * 2, GUIConfig.PADY))

        # Search retry
        search_frame = ttk.Frame(content_frame)
        search_frame.pack(fill="x", pady=(0, GUIConfig.PADY))
        ttk.Label(search_frame, text="Search retry (minutes):").pack(side="left")
        self.search_retry_var = tk.StringVar(value=str(self.app.search_retry_minutes))
        ttk.Entry(search_frame, textvariable=self.search_retry_var, width=10).pack(side="right")

        # Like retry
        like_frame = ttk.Frame(content_frame)
        like_frame.pack(fill="x", pady=(0, GUIConfig.PADY))
        ttk.Label(like_frame, text="Like retry (minutes):").pack(side="left")
        self.like_retry_var = tk.StringVar(value=str(self.app.like_retry_minutes))
        ttk.Entry(like_frame, textvariable=self.like_retry_var, width=10).pack(side="right")

        # Reply retry
        reply_frame = ttk.Frame(content_frame)
        reply_frame.pack(fill="x", pady=(0, GUIConfig.PADY))
        ttk.Label(reply_frame, text="Reply retry (hours):").pack(side="left")
        self.reply_retry_var = tk.StringVar(value=str(self.app.reply_retry_hours))
        ttk.Entry(reply_frame, textvariable=self.reply_retry_var, width=10).pack(side="right")

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
