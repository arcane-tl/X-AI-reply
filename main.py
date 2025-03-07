import tweepy
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
from tkinter.scrolledtext import ScrolledText
import requests
from typing import Optional, Dict, Any, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

# Configuration Classes
class APIConfig:
    BASE_URL = "https://api.twitter.com/2"
    SEARCH_ENDPOINT = f"{BASE_URL}/tweets/search/recent"
    DEFAULT_HEADERS = {"User-Agent": "v2RecentSearchPython"}
    MAX_POST_LENGTH = 280
    MAX_RETRIES = 6
    BUFFER_SECONDS = 15
    MIN_END_TIME_OFFSET = 10
    SECONDS_PER_15M = 15 * 60
    SECONDS_PER_24H = 24 * 60 * 60

class GUIConfig:
    MAIN_SIZE = (800, 800)
    STATUS_SIZE = (600, 400)
    OPTIONS_SIZE = (300, 350)
    PADDING = 10
    PADY = 5

class RateLimits:
    LIMITS = {
        'Free': {
            'search': {'limit': 1, 'window': '15m'},
            'reply': {'limit': 17, 'window': '24h'},
            'like': {'limit': 1, 'window': '15m'}
        },
        'Basic': {
            'search': {'limit': 60, 'window': '15m'},
            'reply': {'limit': 100, 'window': '24h'},
            'like': {'limit': 200, 'window': '24h'}
        },
        'Pro': {
            'search': {'limit': 300, 'window': '15m'},
            'reply': {'limit': 100, 'window': '15m'},
            'like': {'limit': 1000, 'window': '24h'}
        }
    }

# File Constants
LOG_FILE = "api_call_log.json"
OPTIONS_FILE = "user_options.json"

# Load environment variables
if not os.path.exists("cred.env"):
    raise FileNotFoundError("cred.env file not found. Please create it with API credentials.")
load_dotenv("cred.env")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, BEARER_TOKEN]):
    raise ValueError("One or more environment variables are missing. Check your cred.env file.")

# Utility Functions
def get_timestamp() -> str:
    """Return the current timestamp as a formatted string."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def create_client() -> Optional[tweepy.Client]:
    """Create and authenticate a Tweepy client."""
    try:
        return tweepy.Client(
            bearer_token=BEARER_TOKEN,
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET,
            return_type=dict
        )
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        return None

# API Call Logger
class APICallLogger:
    def __init__(self):
        self.logs = []
        self.load_logs()

    def log_call(self, api_ref: str, duration: float, response: Any):
        """Log an API call with its details."""
        timestamp = datetime.datetime.now().isoformat()
        log_entry = {
            'api_ref': api_ref,
            'timestamp': timestamp,
            'duration': duration,
            'response': str(response) if response else "Failed"
        }
        self.logs.append(log_entry)
        self.save_logs()

    def save_logs(self):
        """Save logs to file."""
        with open(LOG_FILE, 'w') as f:
            json.dump(self.logs, f, indent=4)

    def load_logs(self):
        """Load logs from file."""
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                self.logs = json.load(f)
        else:
            self.logs = []

    def get_logs(self) -> list:
        """Return the list of logs."""
        return self.logs

# Statistics Tracker
class APICallStats:
    def __init__(self, logger: APICallLogger, license_level: str = 'Free'):
        self.logger = logger
        self.license_level = license_level

    def set_license_level(self, level: str):
        """Update the license level."""
        self.license_level = level

    def get_avg_duration(self, call_type: str) -> float:
        """Calculate average duration for a call type."""
        api_refs = {
            'search': 'GET /2/tweets/search/recent',
            'reply': 'POST /2/tweets',
            'like': 'POST /2/users/:id/likes'
        }
        durations = [log['duration'] for log in self.logger.get_logs()
                     if log['api_ref'] == api_refs[call_type] and log['response'] != "Failed"]
        return sum(durations) / len(durations) if durations else 0.0

    def format_stats(self) -> str:
        """Format and return API call statistics."""
        output = [f"License Level: {self.license_level}"]
        for call_type in ['search', 'reply', 'like']:
            limit_info = RateLimits.LIMITS[self.license_level][call_type]
            output.append(f"{call_type.capitalize()}:\n"
                          f"  Limit: {limit_info['limit']}/{limit_info['window']}\n"
                          f"  Avg Duration: {self.get_avg_duration(call_type):.2f}s")
        return "\n".join(output)

# GUI Components
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
        """Update the status window with a new message."""
        self.text.config(state="normal")
        self.text.insert(tk.END, f"[{get_timestamp()}] {message}\n")
        self.text.see(tk.END)
        self.text.config(state="disabled")

    def on_close(self):
        """Hide the window instead of closing it."""
        self.window.withdraw()

# Main Application
class xApp:
    def __init__(self, root: tk.Tk, client: tweepy.Client):
        self.root = root
        self.client = client
        self.logger = APICallLogger()
        self.load_user_options()
        self.stats = APICallStats(self.logger, self.license_level.get())
        self.action_queue = Queue()
        self.running_lock = threading.Lock()
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
        """Initialize the GUI layout."""
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        main_x, main_y = 50, (screen_height - GUIConfig.MAIN_SIZE[1]) // 2
        status_x, status_y = main_x + GUIConfig.MAIN_SIZE[0] + 10, main_y
        if status_x + GUIConfig.STATUS_SIZE[0] > screen_width:
            status_x = screen_width - GUIConfig.STATUS_SIZE[0] - 50
        if main_y + GUIConfig.MAIN_SIZE[1] > screen_height:
            main_y = status_y = 50

        self.root.geometry(f"{GUIConfig.MAIN_SIZE[0]}x{GUIConfig.MAIN_SIZE[1]}+{main_x}+{main_y}")
        self.status_window = StatusWindow(self.root, status_x, status_y)
        self.update_status("Application started.")

        input_frame = ttk.Frame(self.root, padding=GUIConfig.PADDING)
        input_frame.pack(fill="x")
        self._setup_input_frame(input_frame)

        ttk.Label(self.root, text="Found Posts (uncheck to exclude from actions):").pack()
        self.post_frame = ttk.Frame(self.root)
        self.post_frame.pack(fill="both", expand=True, pady=GUIConfig.PADY)
        self._setup_scrollable_frame()

        ttk.Label(self.root, text="Actions to Perform:").pack(pady=(GUIConfig.PADY * 2, 0))
        self.action_frame = ttk.Frame(self.root, padding=GUIConfig.PADDING)
        self.action_frame.pack(fill="x")
        self._setup_action_frame()

    def _setup_input_frame(self, frame: ttk.Frame):
        """Set up the input frame with search fields and buttons."""
        ttk.Label(frame, text="Start Date/Time (YYYY-MM-DD HH:MM):").grid(row=0, column=0, sticky="w")
        self.start_entry = ttk.Entry(frame)
        self.start_entry.grid(row=0, column=1, sticky="ew")
        default_start = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
        self.start_entry.insert(0, default_start)

        ttk.Label(frame, text="End Date/Time (YYYY-MM-DD HH:MM):").grid(row=1, column=0, sticky="w")
        self.end_entry = ttk.Entry(frame)
        self.end_entry.grid(row=1, column=1, sticky="ew")
        default_end = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")
        self.end_entry.insert(0, default_end)

        ttk.Label(frame, text="Keywords:").grid(row=2, column=0, sticky="w")
        self.keyword_entry = ttk.Entry(frame, width=40)
        self.keyword_entry.grid(row=2, column=1, sticky="ew")
        self.keyword_entry.insert(0, "python xai")

        ttk.Button(frame, text="Search Posts", command=self.queue_search).grid(row=2, column=2, padx=GUIConfig.PADDING)
        ttk.Button(frame, text="Options", command=self.open_options).grid(row=2, column=3, padx=GUIConfig.PADDING)
        ttk.Button(frame, text="Show Stats", command=self.show_stats).grid(row=2, column=4, padx=GUIConfig.PADDING)

    def _setup_scrollable_frame(self):
        """Set up the scrollable frame for post display."""
        self.canvas = tk.Canvas(self.post_frame)
        self.scrollbar = ttk.Scrollbar(self.post_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.post_check_vars = []

    def _setup_action_frame(self):
        """Set up the action frame with reply and like options."""
        self.reply_var = tk.BooleanVar(value=False)
        self.reply_check = ttk.Checkbutton(self.action_frame, text="Reply to posts", variable=self.reply_var, command=self.toggle_reply_text)
        self.reply_check.pack(anchor="w")
        self.reply_text_frame = ttk.Frame(self.action_frame)
        self.reply_text = tk.Text(self.reply_text_frame, height=4, width=100, state="disabled")
        self.reply_text.pack()
        self.reply_text_frame.pack(anchor="w", padx=(20, 0), pady=GUIConfig.PADY)

        self.like_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.action_frame, text="Like posts", variable=self.like_var).pack(anchor="w")

        self.execute_button = ttk.Button(self.root, text="Execute Actions", command=self.queue_actions, state="disabled")
        self.execute_button.pack(pady=GUIConfig.PADY)
        self.cancel_button = ttk.Button(self.root, text="Cancel Actions", command=self.cancel_actions, state="disabled")
        self.cancel_button.pack(pady=GUIConfig.PADY)

    def load_user_options(self):
        """Load user options from file or set defaults."""
        defaults = {
            'license_level': 'Free',
            'verified_only': False,
            'no_replies': False,
            'retry_interval': 300,
            'debug_mode': False
        }
        options = defaults
        if os.path.exists(OPTIONS_FILE):
            with open(OPTIONS_FILE, 'r') as f:
                options.update(json.load(f))
        
        self.verified_only = tk.BooleanVar(value=options['verified_only'])
        self.no_replies = tk.BooleanVar(value=options['no_replies'])
        self.license_level = tk.StringVar(value=options['license_level'])
        self.retry_interval = options['retry_interval']
        self.debug_mode = tk.BooleanVar(value=options['debug_mode'])

    def save_user_options(self):
        """Save user options to file."""
        options = {
            'license_level': self.license_level.get(),
            'verified_only': self.verified_only.get(),
            'no_replies': self.no_replies.get(),
            'retry_interval': self.retry_interval,
            'debug_mode': self.debug_mode.get()
        }
        with open(OPTIONS_FILE, 'w') as f:
            json.dump(options, f, indent=4)

    def update_status(self, message: str):
        """Update the status window and log the message."""
        logger.info(message)
        self.root.after(0, lambda: self.status_window.update(message))

    def debug_log(self, message: str):
        """Log debug messages to both console and status window if debug mode is enabled."""
        if self.debug_mode.get():
            logger.debug(message)
            self.update_status(f"[DEBUG] {message}")

    def toggle_reply_text(self):
        """Enable or disable the reply text field based on the reply checkbox."""
        state = "normal" if self.reply_var.get() else "disabled"
        self.reply_text.config(state=state)

    def open_options(self):
        """Open the options window and apply changes."""
        options_window = OptionsWindow(self.root, self)
        self.root.wait_window(options_window.window)
        self.verified_only.set(options_window.verified_var.get())
        self.no_replies.set(options_window.no_replies_var.get())
        self.license_level.set(options_window.license_var.get())
        self.retry_interval = int(options_window.retry_interval_var.get()) * 60
        self.debug_mode.set(options_window.debug_var.get())
        self.stats.set_license_level(self.license_level.get())
        self.save_user_options()

    def show_stats(self):
        """Display API call statistics in a new window."""
        stats_window = tk.Toplevel(self.root)
        stats_window.title("API Call Statistics")
        stats_window.geometry("400x300")
        stats_text = tk.Text(stats_window, height=15, width=50)
        stats_text.pack(padx=GUIConfig.PADDING, pady=GUIConfig.PADY)
        stats_text.insert(tk.END, self.stats.format_stats())
        stats_text.config(state="disabled")
        ttk.Button(stats_window, text="Close", command=stats_window.destroy).pack(pady=GUIConfig.PADY)

    def validate_inputs(self) -> Optional[Tuple[str, str, str]]:
        """Validate user inputs and return search parameters."""
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
                self.update_status(f"End time too recent, adjusted from {end_dt.strftime('%Y-%m-%d %H:%M:%S')}Z to {min_end_time.strftime('%Y-%m-%d %H:%M:%S')}Z")
                end_dt = min_end_time
            keywords = self.keyword_entry.get().strip()
            if not keywords:
                raise ValueError("Keywords are required.")
            return keywords, start_dt.isoformat(), end_dt.isoformat()
        except ValueError as e:
            self.update_status(f"Input error: {e}")
            return None

    def queue_search(self):
        """Queue a search action based on user inputs."""
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
        """Queue reply and like actions for selected posts."""
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
        """Cancel all queued actions and stop processing."""
        self.stop_processing_event.set()
        with self.action_queue.mutex:
            self.action_queue.queue.clear()
        self.update_status("All queued actions canceled.")
        self.cancel_button.config(state="disabled")
        self.execute_button.config(state="normal")

    def process_action_queue(self):
        """Process actions from the queue in a separate thread."""
        while True:
            with self.running_lock:
                if not self.running:
                    break
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
                    self.update_status("All actions completed")
            else:
                time.sleep(1)

    def calculate_retry_delay(self, response, call_type: str, retries: int) -> float:
        """Calculate retry delay based on API response headers or fallback."""
        headers = {}
        if response is not None:
            if isinstance(response, requests.models.Response):
                try:
                    headers = dict(response.headers)
                    self.debug_log(f"Headers from requests response: {dict(headers)}")
                except Exception as e:
                    self.debug_log(f"Error accessing headers from requests response: {e}")
            elif hasattr(response, 'headers'):
                try:
                    headers = dict(response.headers)
                    self.debug_log(f"Headers from tweepy response: {dict(headers)}")
                except Exception as e:
                    self.debug_log(f"Error accessing headers from tweepy response: {e}")
            else:
                self.debug_log(f"Response object has no headers attribute: {type(response)}")

        # Check for 24-hour user limit reset
        if 'x-user-limit-24hour-reset' in headers:
            reset_time = headers['x-user-limit-24hour-reset']
            self.debug_log(f"x-user-limit-24hour-reset found with value: '{reset_time}' (type: {type(reset_time)})")
            try:
                reset_time = int(reset_time)
                delay = max(reset_time - int(time.time()), 0) + APIConfig.BUFFER_SECONDS
                self.debug_log(f"x-user-limit-24hour-reset parsed successfully: {reset_time}, calculated delay: {delay}s")
                self.update_status(f"Retry delay for {call_type} set to {delay}s using x-user-limit-24hour-reset")
                return delay
            except ValueError as e:
                self.debug_log(f"Failed to parse x-user-limit-24hour-reset: '{reset_time}' - Error: {e}")

        # Check for standard rate limit reset
        if 'x-rate-limit-reset' in headers:
            reset_time = headers['x-rate-limit-reset']
            self.debug_log(f"x-rate-limit-reset found with value: '{reset_time}' (type: {type(reset_time)})")
            try:
                reset_time = int(reset_time)
                delay = max(reset_time - int(time.time()), 0) + APIConfig.BUFFER_SECONDS
                self.debug_log(f"x-rate-limit-reset parsed successfully: {reset_time}, calculated delay: {delay}s")
                self.update_status(f"Retry delay for {call_type} set to {delay}s using x-rate-limit-reset")
                return delay
            except ValueError as e:
                self.debug_log(f"Failed to parse x-rate-limit-reset: '{reset_time}' - Error: {e}")

        # Fallback to user-defined options
        license_level = self.license_level.get()
        window = RateLimits.LIMITS[license_level][call_type]['window']
        delay = APIConfig.SECONDS_PER_15M if window == '15m' else APIConfig.SECONDS_PER_24H
        self.debug_log(f"No valid reset headers found. Using fallback for {call_type} - License: {license_level}, Window: {window}, Delay: {delay}s")
        self.update_status(f"Retry delay for {call_type} set to {delay}s using fallback ({window})")
        return delay

    def handle_retry(self, action_type: str, params: Dict[str, Any], response: Optional[requests.Response], exception: Exception, call_ref: str, start_time: float) -> bool:
        """Handle retry logic for API calls."""
        duration = time.time() - start_time
        retries = params.get('retries', 0)
        self.logger.log_call(call_ref, duration, None)
        self.debug_log(f"Error: {exception}")

        if retries >= APIConfig.MAX_RETRIES:
            self.update_status(f"Max retries reached for {action_type}")
            self.stop_processing_event.set()
            return False

        delay = self.calculate_retry_delay(response, action_type, retries)
        retry_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
        self.update_status(f"Next {action_type} attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(delay)
        params['retries'] = retries + 1
        self.action_queue.put((action_type, params))
        return True

    def execute_api_call(self, call_func, call_ref: str) -> Tuple[Any, bool]:
        """Execute an API call and log its result."""
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

    def ensure_client(self) -> bool:
        """Ensure the Tweepy client is available."""
        if not self.client:
            self.client = create_client()
            if not self.client:
                self.update_status("API reconnection failed")
                self.stop_processing_event.set()
                return False
        return True

    def perform_search(self, params: Dict[str, Any]):
        """Perform a search for X posts."""
        start_time = time.time()
        query = f"{params['keywords']} -is:retweet"
        if params['verified_only']:
            query += " is:verified"
        if params['no_replies']:
            query += " -is:reply"

        headers = APIConfig.DEFAULT_HEADERS.copy()
        headers["Authorization"] = f"Bearer {BEARER_TOKEN}"
        params_dict = {
            "query": query,
            "start_time": params['start_time'],
            "end_time": params['end_time'],
            "max_results": 10,
            "tweet.fields": "created_at",
            "expansions": "author_id",
            "user.fields": "username"
        }

        def search_call():
            return requests.get(APIConfig.SEARCH_ENDPOINT, headers=headers, params=params_dict)

        try:
            self.debug_log(f"Executing search with query: {query} (retry attempt {params.get('retries', 0) + 1}/{APIConfig.MAX_RETRIES})")
            response, success = self.execute_api_call(search_call, 'GET /2/tweets/search/recent')
            response.raise_for_status()
            posts = response.json()
            self.posts = posts.get('data', [])
            self.users = posts.get('includes', {}).get("users", [])
            self.update_status(f"Search completed. Found {len(self.posts)} posts")
            self.root.after(0, self.update_search_results)
        except requests.exceptions.HTTPError as e:
            is_rate_limit = e.response.status_code == 429
            self.update_status("Search rate limit exceededCHANNEL_TIMEOUT" if is_rate_limit else "Search failed")
            self.handle_retry('search', params, e.response, e, 'GET /2/tweets/search/recent', start_time)
        except Exception as e:
            self.update_status("Search failed")
            self.handle_retry('search', params, None, e, 'GET /2/tweets/search/recent', start_time)

    def perform_reply(self, params: Dict[str, Any]):
        """Reply to an X post."""
        if not self.ensure_client():
            return

        start_time = time.time()
        def reply_call():
            return self.client.create_tweet(text=params['text'], in_reply_to_tweet_id=params['post_id'])

        try:
            self.debug_log(f"Attempting reply to post {params['post_id']} (retry attempt {params.get('retries', 0) + 1}/{APIConfig.MAX_RETRIES})")
            response, success = self.execute_api_call(reply_call, 'POST /2/tweets')
            self.update_status(f"Replied to post {params['post_id']}")
        except (tweepy.TooManyRequests, requests.exceptions.HTTPError) as e:
            is_rate_limit = isinstance(e, tweepy.TooManyRequests) or (hasattr(e, 'response') and e.response.status_code == 429)
            self.update_status("Reply rate limit exceeded" if is_rate_limit else "Reply failed")
            self.handle_retry('reply', params, getattr(e, 'response', None), e, 'POST /2/tweets', start_time)
        except Exception as e:
            self.update_status("Reply failed")
            self.handle_retry('reply', params, None, e, 'POST /2/tweets', start_time)

    def perform_like(self, params: Dict[str, Any]):
        if not self.ensure_client():
            return

        start_time = time.time()
        def like_call():
            return self.client.like(params['post_id'])

        try:
            self.debug_log(f"Attempting to like post {params['post_id']} (retry attempt {params.get('retries', 0) + 1}/{APIConfig.MAX_RETRIES})")
            response, success = self.execute_api_call(like_call, 'POST /2/users/:id/likes')
            self.update_status(f"Liked post {params['post_id']}")
        except tweepy.TooManyRequests as e:
            duration = time.time() - start_time
            self.logger.log_call('POST /2/users/:id/likes', duration, None)
            self.debug_log(f"TooManyRequests error: {e}")
            self.update_status("Like rate limit exceeded")
            self.handle_retry('like', params, e.response, e, 'POST /2/users/:id/likes', start_time)
        except (requests.exceptions.HTTPError, tweepy.TweepyException) as e:
            self.update_status("Like failed")
            self.handle_retry('like', params, getattr(e, 'response', None), e, 'POST /2/users/:id/likes', start_time)

    def update_search_results(self):
        """Update the GUI with search results."""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.post_check_vars.clear()

        if self.posts:
            user_dict = {user['id']: user['username'] for user in self.users}
            for post in self.posts:
                username = user_dict.get(post['author_id'], "Unknown")
                post_frame = ttk.Frame(self.scrollable_frame)
                post_frame.pack(fill="x", pady=2)
                
                check_var = tk.IntVar(value=1)
                ttk.Checkbutton(post_frame, variable=check_var).pack(side="left")
                ttk.Label(post_frame, text=f"@{username}: {post['text']}\n[Posted at: {post['created_at']}]",
                          wraplength=600, justify="left").pack(side="left", fill="x", expand=True)
                
                self.post_check_vars.append((post, check_var))
            self.execute_button.config(state="normal")
        else:
            ttk.Label(self.scrollable_frame, text="No posts found.").pack()
        
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_closing(self):
        """Handle application shutdown."""
        with self.running_lock:
            self.running = False
        self.root.destroy()

# Main Execution
if __name__ == "__main__":
    client = create_client()
    if client is None:
        logger.error("Exiting due to authentication failure.")
    else:
        root = tk.Tk()
        app = xApp(root, client)
        root.mainloop()