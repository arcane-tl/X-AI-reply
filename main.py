import datetime
import json
import os
import time
import threading
import logging
from queue import Queue
from dotenv import load_dotenv
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from config import APIConfig, GUIConfig, RateLimits
from utils import get_timestamp, create_client
from logger import APICallLogger
from stats import APICallStats
from gui_components import OptionsWindow, StatusWindow

# Logging setup
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Load environment variables
if not os.path.exists("cred.env"):
    raise FileNotFoundError("cred.env file not found.")
load_dotenv("cred.env")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, BEARER_TOKEN]):
    raise ValueError("Missing environment variables in cred.env.")

# Constants
LOG_FILE = "api_call_log.json"
OPTIONS_FILE = "user_options.json"

class xApp:
    def __init__(self, root: tk.Tk, client):
        self.root = root
        self.client = client
        self.logger = APICallLogger()
        self.load_user_options()
        self.stats = APICallStats(self.logger, "Free")  # Default license level
        self.action_queue = Queue()
        self.running = True
        self.stop_processing_event = threading.Event()
        self.root.title("X Post Search and Reply")
        self.posts = []
        self.users = []
        self.setup_gui()
        self.processor_thread = threading.Thread(target=self.process_action_queue, daemon=True)
        self.processor_thread.start()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_gui(self):
        # Set up main window
        self.root.geometry("1200x900")
        self.root.minsize(1000, 700)

        # Create main container
        main_container = ttk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Top section - Input controls
        input_section = ttk.LabelFrame(main_container, text="Search Parameters", padding=10)
        input_section.pack(fill="x", pady=(0, 10))
        self._setup_input_frame(input_section)

        # Middle section - Split pane for posts and actions
        content_pane = ttk.PanedWindow(main_container, orient="horizontal")
        content_pane.pack(fill="both", expand=True, pady=(0, 10))

        # Left panel - Search results
        left_panel = ttk.Frame(content_pane)
        content_pane.add(left_panel, weight=2)

        ttk.Label(left_panel, text="Found Posts (uncheck to exclude from actions):").pack(anchor="w", pady=(0, 5))
        self.post_frame = ttk.Frame(left_panel)
        self.post_frame.pack(fill="both", expand=True)
        self._setup_scrollable_frame()

        # Right panel - Actions
        right_panel = ttk.Frame(content_pane)
        content_pane.add(right_panel, weight=1)

        ttk.Label(right_panel, text="Actions to Perform:").pack(anchor="w", pady=(0, 10))
        self.action_frame = ttk.Frame(right_panel, padding=10)
        self.action_frame.pack(fill="both", expand=True)
        self._setup_action_frame()

        # Retry countdown section
        retry_section = ttk.LabelFrame(main_container, text="Retry Countdown", padding=10)
        retry_section.pack(fill="x", pady=(0, 10))

        # Retry status frame
        retry_frame = ttk.Frame(retry_section)
        retry_frame.pack(fill="x")

        self.retry_label = ttk.Label(retry_frame, text="No active retries", font=("TkDefaultFont", 10, "bold"))
        self.retry_label.pack(anchor="w")

        # Progress bar for countdown
        self.retry_progress = ttk.Progressbar(retry_frame, orient="horizontal", length=400, mode="determinate")
        self.retry_progress.pack(fill="x", pady=(5, 0))

        # Countdown timer and cancel button
        timer_frame = ttk.Frame(retry_frame)
        timer_frame.pack(fill="x", pady=(5, 0))

        self.countdown_label = ttk.Label(timer_frame, text="", font=("TkDefaultFont", 9))
        self.countdown_label.pack(side="left")

        self.cancel_retry_button = ttk.Button(timer_frame, text="Cancel Retry", command=self.cancel_current_retry, state="disabled")
        self.cancel_retry_button.pack(side="right")

        # Bottom section - Status and logs
        status_section = ttk.LabelFrame(main_container, text="Status & Logs", padding=10)
        status_section.pack(fill="x", pady=(0, 0))

        # Status text area
        self.status_text = tk.Text(status_section, height=6, wrap="word")
        status_scrollbar = ttk.Scrollbar(status_section, command=self.status_text.yview)
        self.status_text.configure(yscrollcommand=status_scrollbar.set)

        # Make text selectable but prevent editing
        self.status_text.bind("<Key>", lambda e: "break")  # Prevent keyboard input
        self.status_text.bind("<Button-1>", self._start_text_selection)  # Allow selection
        self.status_text.bind("<Button-3>", self._show_context_menu)  # Right-click menu

        self.status_text.pack(side="left", fill="both", expand=True)
        status_scrollbar.pack(side="right", fill="y")

        # Create context menu for text widgets
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Copy", command=self._copy_selected_text)
        self.context_menu.add_command(label="Select All", command=self._select_all_text)

        # Create menu bar
        self._setup_menu_bar()

        # Initialize retry tracking
        self.current_retry_thread = None
        self.retry_cancelled = False

        self.update_status("Application started.")

    def _setup_input_frame(self, frame: ttk.Frame):
        # Configure grid columns
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Start Date/Time (YYYY-MM-DD HH:MM):").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.start_entry = ttk.Entry(frame)
        self.start_entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        default_start = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
        self.start_entry.insert(0, default_start)

        ttk.Label(frame, text="End Date/Time (YYYY-MM-DD HH:MM):").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.end_entry = ttk.Entry(frame)
        self.end_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10))
        default_end = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")
        self.end_entry.insert(0, default_end)

        ttk.Label(frame, text="Keywords:").grid(row=2, column=0, sticky="w", padx=(0, 10))
        self.keyword_entry = ttk.Entry(frame, width=40)
        self.keyword_entry.grid(row=2, column=1, sticky="ew", padx=(0, 10))
        self.keyword_entry.insert(0, "python xai")

        ttk.Button(frame, text="Search Posts", command=self.queue_search).grid(row=2, column=2, padx=(0, 5))
        ttk.Button(frame, text="Options", command=self.open_options).grid(row=2, column=3, padx=(0, 5))
        ttk.Button(frame, text="Show Stats", command=self.show_stats).grid(row=2, column=4, padx=(0, 5))

    def _setup_scrollable_frame(self):
        self.canvas = tk.Canvas(self.post_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.post_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        # Create window and configure scrolling
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Bind events for proper scrolling
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Pack widgets
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.post_check_vars = []

    def _on_frame_configure(self, event):
        """Update scroll region when frame content changes"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Update scroll region when canvas is resized"""
        self.canvas.itemconfig(self.canvas.find_withtag("all")[0], width=event.width)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _setup_action_frame(self):
        self.reply_var = tk.BooleanVar(value=False)
        self.reply_check = ttk.Checkbutton(self.action_frame, text="Reply to posts", variable=self.reply_var,
                                         command=self.toggle_reply_text)
        self.reply_check.pack(anchor="w", pady=(0, 5))

        # Reply text input (initially disabled)
        self.reply_text = tk.Text(self.action_frame, height=3, wrap="word", state="disabled")
        self.reply_text.pack(fill="x", pady=(0, 10))

        self.like_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.action_frame, text="Like posts", variable=self.like_var).pack(anchor="w", pady=(0, 10))

        self.execute_button = ttk.Button(self.action_frame, text="Execute Actions", command=self.queue_actions, state="disabled")
        self.execute_button.pack(pady=GUIConfig.PADY)
        self.cancel_button = ttk.Button(self.action_frame, text="Cancel Actions", command=self.cancel_actions, state="disabled")
        self.cancel_button.pack(pady=GUIConfig.PADY)

    def load_user_options(self):
        defaults = {
            'verified_only': False,
            'no_replies': False,
            'debug_mode': False,
            'search_retry_minutes': 15,
            'like_retry_minutes': 15,
            'reply_retry_hours': 24,
            'max_search_results': 50
        }
        options = defaults
        if os.path.exists(OPTIONS_FILE):
            with open(OPTIONS_FILE, 'r') as f:
                options.update(json.load(f))
        self.verified_only = tk.BooleanVar(value=options['verified_only'])
        self.no_replies = tk.BooleanVar(value=options['no_replies'])
        self.debug_mode = tk.BooleanVar(value=options['debug_mode'])
        self.search_retry_minutes = options['search_retry_minutes']
        self.like_retry_minutes = options['like_retry_minutes']
        self.reply_retry_hours = options['reply_retry_hours']
        self.max_search_results = options['max_search_results']

    def save_user_options(self):
        options = {
            'verified_only': self.verified_only.get(),
            'no_replies': self.no_replies.get(),
            'debug_mode': self.debug_mode.get(),
            'search_retry_minutes': self.search_retry_minutes,
            'like_retry_minutes': self.like_retry_minutes,
            'reply_retry_hours': self.reply_retry_hours,
            'max_search_results': self.max_search_results
        }
        with open(OPTIONS_FILE, 'w') as f:
            json.dump(options, f, indent=4)

    def update_status(self, message: str):
        logger.info(message)
        if hasattr(self, 'status_text'):
            self.root.after(0, lambda: self._update_status_text(message))

    def _update_status_text(self, message: str):
        if hasattr(self, 'status_text'):
            self.status_text.config(state="normal")
            timestamp = get_timestamp()
            self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.status_text.see(tk.END)
            self.status_text.config(state="disabled")

    def debug_log(self, message: str):
        if self.debug_mode.get():
            logger.debug(message)
            self.update_status(f"[DEBUG] {message}")

    def toggle_reply_text(self):
        state = "normal" if self.reply_var.get() else "disabled"
        self.reply_text.config(state=state)

    def open_options(self):
        OptionsWindow(self.root, self)

    def show_stats(self):
        stats_window = tk.Toplevel(self.root)
        stats_window.title("API Call Statistics")
        stats_window.geometry("400x300")
        stats_text = tk.Text(stats_window, height=15, width=50)
        stats_text.pack(padx=GUIConfig.PADDING, pady=GUIConfig.PADY)
        stats_text.insert(tk.END, self.stats.format_stats())
        stats_text.config(state="disabled")
        ttk.Button(stats_window, text="Close", command=stats_window.destroy).pack(pady=GUIConfig.PADY)

    def validate_inputs(self):
        try:
            start_dt = datetime.datetime.strptime(self.start_entry.get(), "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
            end_dt = datetime.datetime.strptime(self.end_entry.get(), "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            if start_dt >= end_dt:
                raise ValueError("End time must be after start time.")
            if start_dt.year < 2006:
                raise ValueError("Start date must be on or after 2006.")
            if start_dt > now:
                raise ValueError("Start time cannot be in the future.")
            min_end_time = now - datetime.timedelta(seconds=APIConfig.MIN_END_TIME_OFFSET)
            if end_dt > min_end_time:
                self.update_status(f"End time adjusted to {min_end_time.strftime('%Y-%m-%d %H:%M:%S')}Z")
                end_dt = min_end_time
            keywords = self.keyword_entry.get().strip()
            if not keywords:
                raise ValueError("Keywords are required.")
            return keywords, start_dt.isoformat(), end_dt.isoformat()
        except ValueError as e:
            self.update_status(f"Input error: {e}")
            return None

    def queue_search(self):
        user_input = self.validate_inputs()
        if user_input is None:
            return
        keywords, start_time, end_time = user_input
        self.action_queue.put(('search', {
            'keywords': keywords,
            'start_time': start_time,
            'end_time': end_time,
            'verified_only': self.verified_only.get(),
            'no_replies': self.no_replies.get(),
            'retries': 0
        }))
        self.update_status("Search queued")

    def queue_actions(self):
        selected_posts = [post for post, var in self.post_check_vars if var.get() == 1]
        if not selected_posts:
            self.update_status("No posts selected")
            return
        if not (self.reply_var.get() or self.like_var.get()):
            self.update_status("No actions selected")
            return

        if self.reply_var.get():
            reply_text = self.reply_text.get("1.0", tk.END).strip()
            if not reply_text:
                messagebox.showwarning("Input Error", "Reply text is required")
                return
            if len(reply_text) > APIConfig.MAX_POST_LENGTH:
                messagebox.showwarning("Length Error", f"Reply exceeds {APIConfig.MAX_POST_LENGTH} characters")
                return
            for post in selected_posts:
                self.action_queue.put(('reply', {'post_id': post['id'], 'text': reply_text, 'retries': 0}))
                self.update_status(f"Reply queued for post {post['id']}")

        if self.like_var.get():
            for post in selected_posts:
                self.action_queue.put(('like', {'post_id': post['id'], 'retries': 0}))
                self.update_status(f"Like queued for post {post['id']}")

        self.cancel_button.config(state="normal")
        self.execute_button.config(state="disabled")

    def cancel_actions(self):
        self.stop_processing_event.set()
        with self.action_queue.mutex:
            self.action_queue.queue.clear()
        self.update_status("All queued actions canceled.")
        self.cancel_button.config(state="disabled")
        self.execute_button.config(state="normal")

    def process_action_queue(self):
        while self.running:
            if self.stop_processing_event.is_set():
                break
            if not self.action_queue.empty():
                action_type, params = self.action_queue.get()
                if action_type == 'search':
                    self.perform_search(params)
                elif action_type == 'reply':
                    self.perform_reply(params)
                elif action_type == 'like':
                    self.perform_like(params)
                self.action_queue.task_done()
                if self.action_queue.empty() and not self.stop_processing_event.is_set():
                    self.root.after(0, lambda: self.update_status("All actions completed"))
            else:
                time.sleep(1)

    def perform_search(self, params):
        start_time = time.time()
        query = f"{params['keywords']} -is:retweet"
        if params['verified_only']:
            query += " is:verified"
        if params['no_replies']:
            query += " -is:reply"
            self.update_status("ℹ️ Excluding replies from search results")
        else:
            self.update_status("ℹ️ Including replies in search results")

        headers = APIConfig.DEFAULT_HEADERS.copy()
        headers["Authorization"] = f"Bearer {BEARER_TOKEN}"
        params_dict = {
            "query": query,
            "start_time": params['start_time'],
            "end_time": params['end_time'],
            "max_results": min(self.max_search_results, 100),  # Twitter API max is 100
            "tweet.fields": "created_at",
            "expansions": "author_id",
            "user.fields": "username"
        }

        def search_call():
            self.update_status("Sending search request to Twitter API...")
            logger.info(f"Search query: {query}, start_time: {params['start_time']}, end_time: {params['end_time']}")
            return requests.get(APIConfig.SEARCH_ENDPOINT, headers=headers, params=params_dict, timeout=30)

        try:
            self.debug_log(f"Executing search: {query}")
            self.update_status("Performing search...")
            response, success = self.execute_api_call(search_call, 'GET /2/tweets/search/recent')
            self.update_status("Search API call completed, processing response...")
            response.raise_for_status()
            posts = response.json()
            self.posts = posts.get('data', [])
            self.users = posts.get('includes', {}).get("users", [])
            self.update_status(f"Search completed. Found {len(self.posts)} posts")
            logger.info(f"Search successful: {len(self.posts)} posts found")
            self.root.after(0, self.update_search_results)
        except requests.exceptions.Timeout:
            self.update_status("⚠️ Search request timed out. Will retry automatically...")
            logger.warning("Search request timed out")
            self.handle_retry('search', params, None, Exception("Timeout"), 'GET /2/tweets/search/recent', start_time)
        except requests.exceptions.HTTPError as e:
            error_details = self._format_api_error_details(
                f"Search HTTP Error ({e.response.status_code})",
                "GET /2/tweets/search/recent",
                params_dict,
                e.response,
                str(e)
            )
            if e.response.status_code == 429:
                self.update_status(f"⚠️ Rate limit exceeded: {error_details}")
            else:
                self.update_status(f"⚠️ Search failed: {error_details}")
            logger.error(f"Search HTTP error: {e}")
            self.handle_retry('search', params, e.response, e, 'GET /2/tweets/search/recent', start_time)
        except Exception as e:
            self.update_status(f"⚠️ Search failed: {str(e)}. Will retry automatically...")
            logger.error(f"Search error: {e}")
            self.handle_retry('search', params, None, e, 'GET /2/tweets/search/recent', start_time)

    def perform_reply(self, params):
        if not self.ensure_client():
            return
        start_time = time.time()

        def reply_call():
            self.update_status("Sending reply to Twitter API...")
            logger.info(f"Replying to post {params['post_id']} with text: {params['text'][:50]}...")
            return self.client.create_tweet(text=params['text'], in_reply_to_tweet_id=params['post_id'])

        try:
            self.debug_log(f"Replying to post {params['post_id']}")
            self.update_status(f"Preparing to reply to post {params['post_id']}...")
            response, success = self.execute_api_call(reply_call, 'POST /2/tweets')
            self.update_status("Reply API call completed, processing response...")
            self.update_status(f"Successfully replied to post {params['post_id']}")
            logger.info(f"Reply successful for post {params['post_id']}")
        except Exception as e:
            # Create request details for error formatting
            request_details = {
                'text': params['text'][:50] + "..." if len(params['text']) > 50 else params['text'],
                'in_reply_to_tweet_id': params['post_id']
            }

            error_details = self._format_api_error_details(
                "Reply Error",
                "POST /2/tweets",
                request_details,
                getattr(e, 'response', None),
                str(e)
            )

            # Check if it's a rate limit error
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                self.update_status(f"⚠️ Reply rate limit exceeded: {error_details}")
            else:
                self.update_status(f"⚠️ Reply failed: {error_details}")

            logger.error(f"Reply failed for post {params['post_id']}: {str(e)}")
            self.handle_retry('reply', params, getattr(e, 'response', None), e, 'POST /2/tweets', start_time)

    def perform_like(self, params):
        if not self.ensure_client():
            return
        start_time = time.time()

        def like_call():
            self.update_status("Sending like to Twitter API...")
            logger.info(f"Liking post {params['post_id']}")
            return self.client.like(params['post_id'])

        try:
            self.debug_log(f"Liking post {params['post_id']}")
            self.update_status(f"Preparing to like post {params['post_id']}...")
            response, success = self.execute_api_call(like_call, 'POST /2/users/:id/likes')
            self.update_status("Like API call completed, processing response...")
            self.update_status(f"Successfully liked post {params['post_id']}")
            logger.info(f"Like successful for post {params['post_id']}")
        except Exception as e:
            # Create request details for error formatting
            request_details = {
                'tweet_id': params['post_id']
            }

            error_details = self._format_api_error_details(
                "Like Error",
                "POST /2/users/:id/likes",
                request_details,
                getattr(e, 'response', None),
                str(e)
            )

            # Check if it's a rate limit error
            if hasattr(e, 'response') and e.response and e.response.status_code == 429:
                self.update_status(f"⚠️ Like rate limit exceeded: {error_details}")
            else:
                self.update_status(f"⚠️ Like failed: {error_details}")

            logger.error(f"Like failed for post {params['post_id']}: {str(e)}")
            self.handle_retry('like', params, getattr(e, 'response', None), e, 'POST /2/users/:id/likes', start_time)

    def update_search_results(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.post_check_vars.clear()

        if self.posts:
            user_dict = {user['id']: user['username'] for user in self.users}
            for post in self.posts:
                username = user_dict.get(post['author_id'], "Unknown")
                post_frame = ttk.Frame(self.scrollable_frame)
                post_frame.pack(fill="x", pady=2, padx=5)
                check_var = tk.IntVar(value=1)
                ttk.Checkbutton(post_frame, variable=check_var).pack(side="left", anchor="n")

                # Create a frame for the post content to handle proper sizing
                content_frame = ttk.Frame(post_frame)
                content_frame.pack(side="left", fill="x", expand=True)

                # Use Text widget for selectable post content with better height calculation
                post_text = tk.Text(content_frame, wrap="word", relief="flat", borderwidth=0,
                                  font=("TkDefaultFont", 9), padx=5, pady=2)
                post_content = f"@{username}: {post['text']}\n[Posted at: {post['created_at']}]"
                post_text.insert("1.0", post_content)
                post_text.config(state="disabled", background=self.root.cget("background"))

                # Calculate required height more accurately
                # Get the width of the text widget to calculate wrapping
                self.root.update_idletasks()  # Ensure widget is rendered
                widget_width = max(400, content_frame.winfo_width() - 20)  # Minimum width with padding

                # Estimate characters per line based on widget width
                chars_per_line = max(40, widget_width // 8)  # Rough estimate: ~8 pixels per character

                # Calculate lines needed
                lines = post_content.count('\n') + 1
                wrapped_lines = max(1, (len(post_content) // chars_per_line) + 1)
                total_lines = max(lines, wrapped_lines)

                # Set height with reasonable limits
                height = min(max(total_lines, 2), 15)  # Min 2 lines, max 15 lines
                post_text.config(height=height)

                post_text.pack(fill="x", expand=True)

                # Make text selectable but prevent editing
                post_text.bind("<Key>", lambda e: "break")  # Prevent keyboard input
                post_text.bind("<Button-1>", self._start_text_selection)  # Allow selection
                post_text.bind("<Button-3>", self._show_context_menu)  # Right-click menu

                self.post_check_vars.append((post, check_var))
            self.execute_button.config(state="normal")
        else:
            ttk.Label(self.scrollable_frame, text="No posts found.").pack()

        # Update scroll region after all widgets are added
        self.root.after(200, self._update_scroll_region)

    def _update_scroll_region(self):
        """Update the scroll region to ensure all content is visible"""
        try:
            self.canvas.update_idletasks()
            # Get the bounding box of all content in the scrollable frame
            bbox = self.canvas.bbox("all")
            if bbox:
                self.canvas.configure(scrollregion=bbox)
            else:
                # Fallback if bbox is None
                self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), self.canvas.winfo_height()))
        except Exception as e:
            logger.error(f"Error updating scroll region: {e}")
            # Fallback scroll region
            self.canvas.configure(scrollregion=(0, 0, 1000, 2000))

    def on_closing(self):
        self.running = False
        self.root.destroy()

    def calculate_retry_delay(self, response, call_type: str, retries: int):
        if response and hasattr(response, 'status_code') and response.status_code == 429:
            # Rate limit exceeded, use reset time from headers
            reset_time = response.headers.get('X-Rate-Limit-Reset')
            if reset_time:
                try:
                    reset_timestamp = int(reset_time)
                    current_time = int(time.time())
                    delay = max(0, reset_timestamp - current_time)
                    self.update_status(f"Rate limit exceeded. Retrying in {delay} seconds (at {datetime.datetime.fromtimestamp(reset_timestamp).strftime('%H:%M:%S')})")
                    return delay
                except (ValueError, TypeError):
                    pass

        # Use configurable retry times when API doesn't provide reset time
        if call_type == 'search':
            delay = self.search_retry_minutes * 60
        elif call_type == 'like':
            delay = self.like_retry_minutes * 60
        elif call_type == 'reply':
            delay = self.reply_retry_hours * 60 * 60
        else:
            delay = 300  # 5 minutes default

        retry_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        self.update_status(f"Using configured retry time. Will retry {call_type} in {delay} seconds (at {retry_time.strftime('%H:%M:%S')})")
        return delay

    def handle_retry(self, action_type: str, params, response, exception, call_ref: str, start_time: float):
        duration = time.time() - start_time
        self.logger.log_call(call_ref, duration, None)
        retries = params.get('retries', 0)

        if retries >= APIConfig.MAX_RETRIES:
            self.update_status(f"❌ Max retries ({APIConfig.MAX_RETRIES}) reached for {action_type}. Operation failed.")
            logger.error(f"Max retries reached for {action_type} on {call_ref}")
            self._clear_retry_display()
            return False

        # Calculate retry delay
        delay = self.calculate_retry_delay(response, action_type, retries)
        retry_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)

        # Start visual countdown
        self._start_retry_countdown(action_type, delay, retries + 1, params, call_ref)

        # Wait for countdown to complete or be cancelled
        self.current_retry_thread.join()

        # Check if retry was cancelled
        if self.retry_cancelled:
            self.update_status(f"⚠️ Retry for {action_type} was cancelled by user")
            self.retry_cancelled = False
            self._clear_retry_display()
            return False

        # Retry was not cancelled, proceed
        params['retries'] = retries + 1
        self.action_queue.put((action_type, params))
        self._clear_retry_display()
        return True

    def execute_api_call(self, call_func, call_ref: str):
        start_time = time.time()
        try:
            response = call_func()
            duration = time.time() - start_time
            self.logger.log_call(call_ref, duration, response)
            return response, True
        except Exception as e:
            duration = time.time() - start_time
            self.logger.log_call(call_ref, duration, None)
            raise e

    def ensure_client(self):
        if not self.client:
            self.client = create_client()
            if not self.client:
                self.update_status("API reconnection failed")
                return False
        return True

    def _start_retry_countdown(self, action_type: str, delay: int, attempt: int, params, call_ref: str):
        """Start visual countdown for retry with progress bar and cancel option"""
        self.retry_cancelled = False

        def countdown_thread():
            try:
                # Update UI elements
                self.root.after(0, lambda: self.retry_label.config(text=f"Retrying {action_type} (attempt {attempt}/{APIConfig.MAX_RETRIES})"))
                self.root.after(0, lambda: self.retry_progress.config(maximum=delay, value=0))
                self.root.after(0, lambda: self.cancel_retry_button.config(state="normal"))

                remaining = delay
                while remaining > 0 and not self.retry_cancelled:
                    # Update countdown display
                    minutes, seconds = divmod(remaining, 60)
                    time_str = f"{minutes:02d}:{seconds:02d}" if minutes > 0 else f"{seconds}s"

                    self.root.after(0, lambda t=time_str, r=remaining, d=delay: self._update_countdown_display(t, r, d))

                    time.sleep(1)
                    remaining -= 1

                if not self.retry_cancelled:
                    # Countdown completed successfully
                    self.root.after(0, lambda: self.retry_label.config(text=f"Retrying {action_type} now..."))
                    self.root.after(0, lambda: self.countdown_label.config(text=""))
                    self.root.after(0, lambda: self.retry_progress.config(value=delay))

            except Exception as e:
                logger.error(f"Error in countdown thread: {e}")

        self.current_retry_thread = threading.Thread(target=countdown_thread, daemon=True)
        self.current_retry_thread.start()

    def _update_countdown_display(self, time_str: str, remaining: int, total: int):
        """Update the countdown display elements"""
        self.countdown_label.config(text=f"Time remaining: {time_str}")
        self.retry_progress.config(value=total - remaining)

    def cancel_current_retry(self):
        """Cancel the current retry countdown"""
        if self.current_retry_thread and self.current_retry_thread.is_alive():
            self.retry_cancelled = True
            self.update_status("Cancelling retry...")

    def _clear_retry_display(self):
        """Clear the retry countdown display"""
        self.root.after(0, lambda: self.retry_label.config(text="No active retries"))
        self.root.after(0, lambda: self.countdown_label.config(text=""))
        self.root.after(0, lambda: self.retry_progress.config(value=0))
        self.root.after(0, lambda: self.cancel_retry_button.config(state="disabled"))



    def _start_text_selection(self, event):
        """Allow text selection in read-only text widgets"""
        # Get the text widget that triggered the event
        text_widget = event.widget
        # Allow normal text selection behavior
        text_widget.focus_set()
        return "break"

    def _show_context_menu(self, event):
        """Show context menu for text widgets"""
        try:
            # Store reference to the text widget that was right-clicked
            self.current_text_widget = event.widget
            # Show context menu at mouse position
            self.context_menu.post(event.x_root, event.y_root)
        finally:
            # Prevent default right-click behavior
            return "break"

    def _copy_selected_text(self):
        """Copy selected text to clipboard"""
        if hasattr(self, 'current_text_widget'):
            try:
                selected_text = self.current_text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                if selected_text:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(selected_text)
                    self.update_status("Text copied to clipboard")
            except tk.TclError:
                # No text selected
                self.update_status("No text selected to copy")

    def _select_all_text(self):
        """Select all text in the current text widget"""
        if hasattr(self, 'current_text_widget'):
            self.current_text_widget.tag_add(tk.SEL, "1.0", tk.END)
            self.current_text_widget.mark_set(tk.INSERT, tk.END)
            self.current_text_widget.see(tk.INSERT)

    def _setup_menu_bar(self):
        """Set up the application menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="API Diagnostics", command=self._run_api_diagnostics)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo("About", "X Post Search and Reply Tool\nVersion 1.0\n\nA tool for searching and interacting with X (Twitter) posts.")

    def _run_api_diagnostics(self):
        """Run diagnostics to check common API issues"""
        diag_window = tk.Toplevel(self.root)
        diag_window.title("API Diagnostics")
        diag_window.geometry("600x400")
        diag_window.transient(self.root)

        content_frame = ttk.Frame(diag_window, padding=15)
        content_frame.pack(fill="both", expand=True)

        # Header
        header_label = ttk.Label(content_frame, text="🔧 API Diagnostics",
                                font=("TkDefaultFont", 12, "bold"))
        header_label.pack(anchor="w", pady=(0, 10))

        # Results text area
        text_frame = ttk.Frame(content_frame)
        text_frame.pack(fill="both", expand=True)

        diag_text = tk.Text(text_frame, wrap="word", font=("TkDefaultFont", 9))
        scrollbar = ttk.Scrollbar(text_frame, command=diag_text.yview)
        diag_text.configure(yscrollcommand=scrollbar.set)

        diag_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Run diagnostics
        def run_checks():
            diag_text.delete("1.0", tk.END)
            diag_text.insert("1.0", "🔍 Running API Diagnostics...\n\n")

            # Check 1: Credentials file
            diag_text.insert(tk.END, "📁 Checking credentials file...\n")
            if os.path.exists("cred.env"):
                diag_text.insert(tk.END, "✅ cred.env file exists\n")
            else:
                diag_text.insert(tk.END, "❌ cred.env file missing - create this file with your API credentials\n")

            # Check 2: Environment variables
            diag_text.insert(tk.END, "\n🔑 Checking API credentials...\n")
            required_vars = ['API_KEY', 'API_SECRET', 'ACCESS_TOKEN', 'ACCESS_TOKEN_SECRET', 'BEARER_TOKEN']
            missing_vars = []
            for var in required_vars:
                if not os.getenv(var):
                    missing_vars.append(var)
                else:
                    diag_text.insert(tk.END, f"✅ {var} is set\n")

            if missing_vars:
                diag_text.insert(tk.END, f"❌ Missing credentials: {', '.join(missing_vars)}\n")
                diag_text.insert(tk.END, "   Add these to your cred.env file\n")

            # Check 3: API permissions
            diag_text.insert(tk.END, "\n🔐 Checking API permissions...\n")
            diag_text.insert(tk.END, "ℹ️  For write operations (likes, replies), ensure your app has:\n")
            diag_text.insert(tk.END, "   • Read and Write permissions in Twitter Developer Portal\n")
            diag_text.insert(tk.END, "   • OAuth 1.1a authentication (not just Bearer token)\n")

            # Check 4: Common issues
            diag_text.insert(tk.END, "\n🚨 Common Issues & Solutions:\n\n")

            diag_text.insert(tk.END, "400 Bad Request:\n")
            diag_text.insert(tk.END, "• Check tweet length (max 280 characters)\n")
            diag_text.insert(tk.END, "• Verify date formats in search parameters\n")
            diag_text.insert(tk.END, "• Ensure tweet IDs are valid\n\n")

            diag_text.insert(tk.END, "403 Forbidden:\n")
            diag_text.insert(tk.END, "• Enable write permissions in Developer Portal\n")
            diag_text.insert(tk.END, "• Use OAuth 1.1a (not just Bearer token)\n")
            diag_text.insert(tk.END, "• Check if target tweet is protected/private\n\n")

            diag_text.insert(tk.END, "401 Unauthorized:\n")
            diag_text.insert(tk.END, "• Regenerate API keys and tokens\n")
            diag_text.insert(tk.END, "• Check token expiration\n")
            diag_text.insert(tk.END, "• Verify app permissions\n\n")

            diag_text.insert(tk.END, "429 Rate Limited:\n")
            diag_text.insert(tk.END, "• Wait for rate limit to reset\n")
            diag_text.insert(tk.END, "• Reduce request frequency\n")
            diag_text.insert(tk.END, "• Consider upgrading API plan\n")

            diag_text.config(state="disabled")

        # Run diagnostics on window open
        diag_window.after(100, run_checks)

        # Buttons
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill="x", pady=(15, 0))

        def close_window():
            diag_window.destroy()

        ttk.Button(button_frame, text="Close", command=close_window).pack(side="right")

        # Handle window close
        diag_window.protocol("WM_DELETE_WINDOW", close_window)

    def _format_api_error_details(self, error_type, endpoint, request_params, response, error_message):
        """Format comprehensive API error details for better debugging"""
        details = f"{error_type}: {error_message}"

        # Add request information
        details += f"\n📡 Endpoint: {endpoint}"

        if request_params:
            # Mask sensitive information
            safe_params = {}
            for key, value in request_params.items():
                if 'token' in key.lower() or 'key' in key.lower():
                    safe_params[key] = "***MASKED***"
                else:
                    safe_params[key] = value
            details += f"\n📋 Parameters: {safe_params}"

        # Add response information if available
        if response:
            details += f"\n📊 Status Code: {response.status_code}"

            # Add specific troubleshooting for common errors
            if response.status_code == 400:
                details += "\n🚨 400 Bad Request - Common causes:"
                details += "\n   • Invalid request parameters or malformed data"
                details += "\n   • Tweet text too long or contains invalid characters"
                details += "\n   • Invalid date format in search parameters"
                details += "\n   • Duplicate tweet content"
                details += "\n💡 Check your input data and try again"
            elif response.status_code == 403:
                details += "\n🚫 403 Forbidden - Common causes:"
                details += "\n   • Missing write permissions for likes/replies"
                details += "\n   • Tweet is protected/private"
                details += "\n   • Account suspended or restricted"
                details += "\n   • Missing OAuth write scope"
                details += "\n💡 Check your app permissions and tweet visibility"

            # Try to get Twitter API error details
            try:
                if hasattr(response, 'json'):
                    error_data = response.json()
                    if 'errors' in error_data and error_data['errors']:
                        api_error = error_data['errors'][0]
                        if 'message' in api_error:
                            details += f"\n❌ API Message: {api_error['message']}"
                        if 'code' in api_error:
                            details += f"\n🔢 Error Code: {api_error['code']}"
                            # Add documentation link for common errors
                            doc_link = self._get_error_documentation_link(api_error['code'])
                            if doc_link:
                                details += f"\n📖 Documentation: {doc_link}"

                            # Add specific troubleshooting for common error codes
                            troubleshooting = self._get_error_troubleshooting(api_error['code'])
                            if troubleshooting:
                                details += f"\n🔧 Troubleshooting: {troubleshooting}"
            except Exception:
                pass

            # Add rate limit information if available
            if hasattr(response, 'headers'):
                rate_limit_remaining = response.headers.get('X-Rate-Limit-Remaining')
                rate_limit_reset = response.headers.get('X-Rate-Limit-Reset')
                if rate_limit_remaining:
                    details += f"\n⏱️ Rate Limit Remaining: {rate_limit_remaining}"
                if rate_limit_reset:
                    try:
                        reset_time = datetime.datetime.fromtimestamp(int(rate_limit_reset))
                        details += f"\n🔄 Rate Limit Resets: {reset_time.strftime('%H:%M:%S UTC')}"
                    except:
                        details += f"\n🔄 Rate Limit Reset: {rate_limit_reset}"

        return details

    def _get_error_documentation_link(self, error_code):
        """Get documentation link for common Twitter API error codes"""
        error_links = {
            32: "https://developer.twitter.com/en/docs/authentication/api-reference/authenticate",
            34: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/lookup/api-reference/get-tweets-id",
            36: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            44: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            64: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            88: "https://developer.twitter.com/en/docs/rate-limits",
            89: "https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code",
            99: "https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code",
            130: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/search/api-reference/get-tweets-search-recent",
            131: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/search/api-reference/get-tweets-search-recent",
            135: "https://developer.twitter.com/en/docs/authentication/api-reference/authenticate",
            144: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/delete-tweets-id",
            179: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/lookup/api-reference/get-tweets-id",
            185: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            186: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            187: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            200: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            220: "https://developer.twitter.com/en/docs/rate-limits",
            226: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/filtered-stream/api-reference/get-tweets-search-stream",
            261: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            326: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            327: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            349: "https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code",
            415: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets",
            416: "https://developer.twitter.com/en/docs/twitter-api/v2/tweets/manage-tweets/api-reference/post-tweets"
        }
        return error_links.get(error_code)

    def _get_error_troubleshooting(self, error_code):
        """Get specific troubleshooting steps for common Twitter API error codes"""
        troubleshooting = {
            32: "Your app's API keys are invalid. Regenerate them in the Twitter Developer Portal.",
            34: "The tweet you're trying to access doesn't exist or has been deleted.",
            36: "You don't have permission to perform this action on this tweet.",
            44: "This tweet has already been liked by your account.",
            64: "Your account is suspended and cannot perform write actions.",
            88: "Rate limit exceeded. Wait for the reset time shown above, or upgrade your API plan.",
            89: "Your access token has expired. Re-authenticate your application.",
            99: "Unable to verify your credentials. Check your API keys and access tokens.",
            130: "Twitter is temporarily over capacity. Wait a few minutes and try again.",
            131: "Internal Twitter error. This is usually temporary - try again later.",
            135: "Authentication failed. Check your API keys, tokens, and OAuth flow.",
            144: "The tweet you're trying to delete doesn't exist or isn't yours to delete.",
            179: "You don't have permission to view this tweet (it's protected).",
            185: "You are posting too frequently. Wait before posting again.",
            186: "Your tweet is too long. Shorten it to fit within Twitter's character limit.",
            187: "You're trying to post a duplicate tweet. Twitter doesn't allow exact duplicates.",
            200: "You can't reply to a tweet that doesn't allow replies.",
            220: "Your credentials don't have the required permissions for this action.",
            226: "This request looks like it might be automated. Twitter may have flagged your activity.",
            261: "Application cannot perform write actions. Check your app permissions in Developer Portal.",
            326: "You have been temporarily locked out due to unusual activity. Wait and try again.",
            327: "You cannot reply to this tweet (it may be from a blocked account).",
            349: "You don't have the correct OAuth scope for this operation.",
            415: "Unsupported media type. Check your file format and try again.",
            416: "The tweet you're trying to reply to doesn't exist."
        }
        return troubleshooting.get(error_code)
