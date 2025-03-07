import tweepy
import datetime
import json
import os
import time
import threading
from queue import Queue
from dotenv import load_dotenv
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import requests

# Constants
MAX_POST_LENGTH = 280  # X's character limit
MAX_RETRIES = 6  # Maximum retry attempts for rate limits
LOG_FILE = "api_call_log.json"  # File for API call logs
OPTIONS_FILE = "user_options.json"  # File for user options

# Load environment variables from cred.env
load_dotenv("cred.env")

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, BEARER_TOKEN]):
    raise ValueError("One or more environment variables are missing. Check your cred.env file.")

# Authenticate with X API v2
def create_client():
    try:
        client = tweepy.Client(
            bearer_token=BEARER_TOKEN,
            consumer_key=API_KEY,
            consumer_secret=API_SECRET,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET,
            return_type=dict  # Ensure raw dict responses for debugging
        )
        return client
    except Exception as e:
        timestamp = get_timestamp()
        print(f"[{timestamp}] Authentication failed: {e}")
        return None

# Helper function to get current timestamp
def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# API Rate Limits based on provided values
RATE_LIMITS = {
    'Free': {
        'search': {'limit': 1, 'window': '15m'},    # 1 req/15 mins
        'reply': {'limit': 17, 'window': '24h'},    # 17 req/24 hours
        'like': {'limit': 1, 'window': '15m'}       # 1 req/15 mins
    },
    'Basic': {
        'search': {'limit': 60, 'window': '15m'},   # 60 req/15 mins
        'reply': {'limit': 100, 'window': '24h'},   # 100 req/24 hours
        'like': {'limit': 200, 'window': '24h'}     # 200 req/24 hours
    },
    'Pro': {
        'search': {'limit': 300, 'window': '15m'},  # 300 req/15 mins
        'reply': {'limit': 100, 'window': '15m'},   # 100 req/15 mins
        'like': {'limit': 1000, 'window': '24h'}    # 1000 req/24 hours
    }
}

# API Call Logger Class
class APICallLogger:
    def __init__(self):
        self.logs = []
        self.load_logs()

    def log_call(self, api_ref, duration, response):
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
        with open(LOG_FILE, 'w') as f:
            json.dump(self.logs, f, indent=4)

    def load_logs(self):
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                self.logs = json.load(f)
        else:
            self.logs = []

    def get_logs(self):
        return self.logs

# Statistics Tracker Class using Log Data
class APICallStats:
    def __init__(self, logger, license_level='Free'):
        self.logger = logger
        self.license_level = license_level

    def set_license_level(self, level):
        self.license_level = level

    def get_retry_delay(self, call_type):
        now = datetime.datetime.now()
        limit_info = RATE_LIMITS[self.license_level][call_type]
        window = limit_info['window']
        delta = datetime.timedelta(minutes=15) if window == '15m' else datetime.timedelta(hours=24)
        
        api_refs = {
            'search': 'GET /2/tweets/search/recent',
            'reply': 'POST /2/tweets',
            'like': 'POST /2/users/:id/likes'
        }
        
        successful_calls = [log for log in self.logger.get_logs()
                           if log['api_ref'] == api_refs[call_type]
                           and log['response'] != "Failed"]
        
        if not successful_calls:
            return None
        
        successful_calls.sort(key=lambda x: datetime.datetime.fromisoformat(x['timestamp']), reverse=True)
        last_call = successful_calls[0]
        last_call_time = datetime.datetime.fromisoformat(last_call['timestamp'])
        next_possible_time = last_call_time + delta
        delay = (next_possible_time - now).total_seconds()
        
        return max(delay, 0)

    def get_last_call(self, call_type):
        api_refs = {
            'search': 'GET /2/tweets/search/recent',
            'reply': 'POST /2/tweets',
            'like': 'POST /2/users/:id/likes'
        }
        logs = [log for log in self.logger.get_logs() if log['api_ref'] == api_refs[call_type]]
        if logs:
            return datetime.datetime.fromisoformat(logs[-1]['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
        return "Never"

    def get_avg_duration(self, call_type):
        api_refs = {
            'search': 'GET /2/tweets/search/recent',
            'reply': 'POST /2/tweets',
            'like': 'POST /2/users/:id/likes'
        }
        durations = [log['duration'] for log in self.logger.get_logs()
                    if log['api_ref'] == api_refs[call_type] and log['response'] != "Failed"]
        return sum(durations) / len(durations) if durations else 0.0

    def format_stats(self):
        output = [f"License Level: {self.license_level}"]
        for call_type in ['search', 'reply', 'like']:
            limit_info = RATE_LIMITS[self.license_level][call_type]
            limit = limit_info['limit']
            window = limit_info['window']
            last_call = self.get_last_call(call_type)
            avg_time = self.get_avg_duration(call_type)
            output.append(f"{call_type.capitalize()}:\n"
                         f"  Limit: {limit}/{window}\n"
                         f"  Last Call: {last_call}\n"
                         f"  Avg Duration: {avg_time:.2f}s")
        return "\n".join(output)

# Options Popup Window
class OptionsWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Options")
        self.window.geometry("300x350")
        self.window.transient(parent)
        self.window.grab_set()

        content_frame = ttk.Frame(self.window, padding="10")
        content_frame.pack(anchor="nw")

        bold_font = ("TkDefaultFont", 10, "bold")
        
        search_label = ttk.Label(content_frame, text="Search Options:", font=bold_font)
        search_label.pack(anchor="w", pady=(0, 5))
        self.verified_var = tk.BooleanVar(value=self.app.verified_only.get())
        ttk.Checkbutton(content_frame, text="Search only for posts by verified accounts", variable=self.verified_var).pack(anchor="w")
        self.no_replies_var = tk.BooleanVar(value=self.app.no_replies.get())
        ttk.Checkbutton(content_frame, text="Do not include replies in search", variable=self.no_replies_var).pack(anchor="w")

        license_label = ttk.Label(content_frame, text="API License Level:", font=bold_font)
        license_label.pack(anchor="w", pady=(10, 5))
        self.license_var = tk.StringVar(value=self.app.license_level.get())
        license_options = ttk.Combobox(content_frame, textvariable=self.license_var, values=list(RATE_LIMITS.keys()), state="readonly")
        license_options.pack(anchor="w")

        retry_label = ttk.Label(content_frame, text="Fallback Retry Interval:", font=bold_font)
        retry_label.pack(anchor="w", pady=(10, 5))
        self.retry_interval_var = tk.StringVar(value=str(self.app.retry_interval // 60))
        retry_options = ttk.Combobox(content_frame, textvariable=self.retry_interval_var, values=["5", "15", "30", "60"], state="readonly")
        retry_options.pack(anchor="w")
        ttk.Label(content_frame, text="(in minutes)").pack(anchor="w")

        debug_label = ttk.Label(content_frame, text="Debug Options:", font=bold_font)
        debug_label.pack(anchor="w", pady=(10, 5))
        self.debug_var = tk.BooleanVar(value=self.app.debug_mode.get())
        ttk.Checkbutton(content_frame, text="Enable debug logging", variable=self.debug_var).pack(anchor="w")

        ttk.Button(content_frame, text="Close", command=self.window.destroy).pack(anchor="w", pady=10)

# Status Window
class StatusWindow:
    def __init__(self, parent, x, y):
        self.window = tk.Toplevel(parent)
        self.window.title("Status Log")
        self.window.geometry(f"600x400+{x}+{y}")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        self.text = ScrolledText(self.window, height=20, width=80, wrap=tk.WORD)
        self.text.pack(fill="both", expand=True, padx=10, pady=10)
        self.text.config(state="disabled")

    def update(self, message):
        self.text.config(state="normal")
        self.text.insert(tk.END, f"[{get_timestamp()}] {message}\n")
        self.text.see(tk.END)
        self.text.config(state="disabled")

    def on_close(self):
        self.window.withdraw()

# GUI Application Class
class xApp:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.logger = APICallLogger()
        self.load_user_options()
        self.stats = APICallStats(self.logger, self.license_level.get())
        self.action_queue = Queue()
        self.running = True
        self.stop_processing = False
        self.root.title("X Post Search and Reply")

        self.posts = []
        self.users = []

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        main_width = 800
        main_height = 800
        status_width = 600
        status_height = 400
        
        main_x = 50
        main_y = (screen_height - main_height) // 2
        status_x = main_x + main_width + 10
        status_y = main_y
        
        if status_x + status_width > screen_width:
            status_x = screen_width - status_width - 50
        if main_y + main_height > screen_height:
            main_y = status_y = 50

        self.root.geometry(f"{main_width}x{main_height}+{main_x}+{main_y}")
        self.status_window = StatusWindow(self.root, status_x, status_y)
        self.update_status("Application started.")

        input_frame = ttk.Frame(self.root, padding="10")
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text="Start Date/Time (YYYY-MM-DD HH:MM):").grid(row=0, column=0, sticky="w")
        self.start_entry = ttk.Entry(input_frame)
        self.start_entry.grid(row=0, column=1, sticky="ew")
        default_start = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
        self.start_entry.insert(0, default_start)

        ttk.Label(input_frame, text="End Date/Time (YYYY-MM-DD HH:MM):").grid(row=1, column=0, sticky="w")
        self.end_entry = ttk.Entry(input_frame)
        self.end_entry.grid(row=1, column=1, sticky="ew")
        default_end = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M")
        self.end_entry.insert(0, default_end)

        ttk.Label(input_frame, text="Keywords:").grid(row=2, column=0, sticky="w")
        self.keyword_entry = ttk.Entry(input_frame, width=40)
        self.keyword_entry.grid(row=2, column=1, sticky="ew")
        self.keyword_entry.insert(0, "python xai")

        self.search_button = ttk.Button(input_frame, text="Search Posts", command=self.queue_search)
        self.search_button.grid(row=2, column=2, padx=10)

        self.options_button = ttk.Button(input_frame, text="Options", command=self.open_options)
        self.options_button.grid(row=2, column=3, padx=10)

        self.stats_button = ttk.Button(input_frame, text="Show Stats", command=self.show_stats)
        self.stats_button.grid(row=2, column=4, padx=10)

        ttk.Label(self.root, text="Found Posts (uncheck to exclude from actions):").pack()
        self.post_frame = ttk.Frame(self.root)
        self.post_frame.pack(fill="both", expand=True, pady=5)
        self.canvas = tk.Canvas(self.post_frame)
        self.scrollbar = ttk.Scrollbar(self.post_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        ttk.Label(self.root, text="Actions to Perform:").pack(pady=(10, 0))
        self.action_frame = ttk.Frame(self.root, padding="10")
        self.action_frame.pack(fill="x")

        self.reply_var = tk.BooleanVar(value=False)
        self.reply_check = ttk.Checkbutton(self.action_frame, text="Reply to posts", variable=self.reply_var, command=self.toggle_reply_text)
        self.reply_check.pack(anchor="w")
        self.reply_text_frame = ttk.Frame(self.action_frame)
        self.reply_text = tk.Text(self.reply_text_frame, height=4, width=100, state="disabled")
        self.reply_text.pack()
        self.reply_text_frame.pack(anchor="w", padx=(20, 0), pady=5)

        self.like_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.action_frame, text="Like posts", variable=self.like_var).pack(anchor="w")

        self.execute_button = ttk.Button(self.root, text="Execute Actions", command=self.queue_actions, state="disabled")
        self.execute_button.pack(pady=5)

        self.post_check_vars = []

        self.processor_thread = threading.Thread(target=self.process_action_queue, daemon=True)
        self.processor_thread.start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_user_options(self):
        defaults = {
            'license_level': 'Free',
            'verified_only': False,
            'no_replies': False,
            'retry_interval': 300,
            'debug_mode': False
        }
        if os.path.exists(OPTIONS_FILE):
            with open(OPTIONS_FILE, 'r') as f:
                options = json.load(f)
        else:
            options = defaults
        
        self.verified_only = tk.BooleanVar(value=options.get('verified_only', defaults['verified_only']))
        self.no_replies = tk.BooleanVar(value=options.get('no_replies', defaults['no_replies']))
        self.license_level = tk.StringVar(value=options.get('license_level', defaults['license_level']))
        self.retry_interval = options.get('retry_interval', defaults['retry_interval'])
        self.debug_mode = tk.BooleanVar(value=options.get('debug_mode', defaults['debug_mode']))

    def save_user_options(self):
        options = {
            'license_level': self.license_level.get(),
            'verified_only': self.verified_only.get(),
            'no_replies': self.no_replies.get(),
            'retry_interval': self.retry_interval,
            'debug_mode': self.debug_mode.get()
        }
        with open(OPTIONS_FILE, 'w') as f:
            json.dump(options, f, indent=4)

    def update_status(self, message):
        self.root.after(0, lambda: self.status_window.update(message))

    def debug_log(self, message):
        if self.debug_mode.get():
            self.update_status(f"DEBUG: {message}")

    def toggle_reply_text(self):
        state = "normal" if self.reply_var.get() else "disabled"
        self.reply_text.config(state=state)

    def open_options(self):
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
        stats_window = tk.Toplevel(self.root)
        stats_window.title("API Call Statistics")
        stats_window.geometry("400x300")
        stats_text = tk.Text(stats_window, height=15, width=50)
        stats_text.pack(padx=10, pady=10)
        stats_text.insert(tk.END, self.stats.format_stats())
        stats_text.config(state="disabled")
        ttk.Button(stats_window, text="Close", command=stats_window.destroy).pack(pady=5)

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
            min_end_time = now - datetime.timedelta(seconds=10)
            if end_dt > min_end_time:
                self.update_status(f"End time adjusted to {min_end_time.strftime('%Y-%m-%d %H:%M:%S')}Z")
                end_dt = min_end_time
            start_time = start_dt.isoformat()
            end_time = end_dt.isoformat()
            keywords = self.keyword_entry.get().strip()
            if not keywords:
                raise ValueError("Keywords are required.")
            return keywords, start_time, end_time
        except ValueError as e:
            self.update_status(f"Input error: {str(e)}")
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
            if len(reply_text) > MAX_POST_LENGTH:
                messagebox.showwarning("Length Error", f"Reply exceeds {MAX_POST_LENGTH} characters")
                return
            for post in selected_posts:
                self.action_queue.put(('reply', {'post_id': post['id'], 'text': reply_text, 'retries': 0}))
                self.update_status(f"Reply queued for post {post['id']}")

        if self.like_var.get():
            for post in selected_posts:
                self.action_queue.put(('like', {'post_id': post['id'], 'retries': 0}))
                self.update_status(f"Like queued for post {post['id']}")

        self.execute_button.config(state="disabled")

    def process_action_queue(self):
        self.stop_processing = False
        while self.running and not self.stop_processing:
            if not self.action_queue.empty():
                action_type, params = self.action_queue.get()
                retries = params.get('retries', 0)
                if action_type == 'search':
                    self.perform_search(params)
                elif action_type == 'reply':
                    self.perform_reply(params)
                elif action_type == 'like':
                    self.perform_like(params)
                self.action_queue.task_done()
                if self.action_queue.empty() and not self.stop_processing:
                    self.update_status("All actions completed")
            else:
                time.sleep(1)

    def calculate_retry_delay(self, response, call_type, retries):
        """Calculate the retry delay based on X API response headers or fallback."""
        headers = {}
        delay = None

        if response is not None:
            if isinstance(response, requests.models.Response):
                try:
                    headers = dict(response.headers)
                    self.debug_log(f"Headers from requests response: {headers}")
                except Exception as e:
                    self.debug_log(f"Error accessing headers from requests response: {e}")
            elif hasattr(response, 'headers'):
                try:
                    headers = dict(response.headers)
                    self.debug_log(f"Headers from tweepy response: {headers}")
                except Exception as e:
                    self.debug_log(f"Error accessing headers from tweepy response: {e}")
            else:
                self.debug_log(f"Response object has no headers attribute: {type(response)}")

            reset_key = next((key for key in headers if key.lower() == 'x-rate-limit-reset'), None)
            standard_reset_delay = None
            if reset_key:
                try:
                    reset_time = int(headers[reset_key])
                    current_time = int(time.time())
                    standard_reset_delay = max(reset_time - current_time, 0) + 15  # Add 15s buffer (5s + 10s)
                    self.debug_log(f"Standard rate limit reset: {reset_time} (delay: {standard_reset_delay}s)")
                except ValueError as e:
                    self.debug_log(f"Invalid x-rate-limit-reset value: {headers[reset_key]} ({e})")

            user_reset_key = next((key for key in headers if key.lower() == 'x-user-limit-24hour-reset'), None)
            user_reset_delay = None
            if user_reset_key:
                try:
                    user_reset_time = int(headers[user_reset_key])
                    current_time = int(time.time())
                    user_reset_delay = max(user_reset_time - current_time, 0) + 15  # Add 15s buffer (5s + 10s)
                    self.debug_log(f"24-hour user limit reset: {user_reset_time} (delay: {user_reset_delay}s)")
                except ValueError as e:
                    self.debug_log(f"Invalid x-user-limit-24hour-reset value: {headers[user_reset_key]} ({e})")

            if standard_reset_delay is not None and user_reset_delay is not None:
                delay = max(standard_reset_delay, user_reset_delay)
                self.debug_log(f"Using longer delay: {delay}s (standard: {standard_reset_delay}s, 24-hour: {user_reset_delay}s)")
            elif standard_reset_delay is not None:
                delay = standard_reset_delay
            elif user_reset_delay is not None:
                delay = user_reset_delay

            if delay is not None:
                return delay

        # Fallback
        limit_info = RATE_LIMITS[self.license_level.get()][call_type]
        window = limit_info['window']
        window_seconds = 15 * 60 if window == '15m' else 24 * 60 * 60
        delay = window_seconds
        self.debug_log(f"No valid reset headers. Using window-based delay ({window}): {delay}s")
        return delay

    def perform_search(self, params):
        start_time = time.time()
        keywords = params['keywords']
        start_time_input = params['start_time']
        end_time = params['end_time']
        retries = params.get('retries', 0)

        query = f"{keywords} -is:retweet"
        if params['verified_only']:
            query += " is:verified"
        if params['no_replies']:
            query += " -is:reply"

        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {BEARER_TOKEN}", "User-Agent": "v2RecentSearchPython"}
        params_dict = {
            "query": query,
            "start_time": start_time_input,
            "end_time": end_time,
            "max_results": 10,
            "tweet.fields": "created_at",
            "expansions": "author_id",
            "user.fields": "username"
        }

        try:
            self.debug_log(f"Executing search with query: {query} (retry attempt {retries + 1}/{MAX_RETRIES})")
            response = requests.get(url, headers=headers, params=params_dict)
            self.debug_log(f"Request URL: {response.url}")
            response.raise_for_status()

            posts = response.json()
            duration = time.time() - start_time
            self.logger.log_call('GET /2/tweets/search/recent', duration, posts)
            self.posts = posts.get('data', []) if posts else []
            self.users = posts.get('includes', {}).get("users", []) if posts else []
            self.update_status(f"Search completed. Found {len(self.posts)} posts")
            self.root.after(0, self.update_search_results)

        except requests.exceptions.HTTPError as e:
            duration = time.time() - start_time
            self.logger.log_call('GET /2/tweets/search/recent', duration, None)
            self.debug_log(f"HTTP error: {e}")
            if response.status_code == 429:
                self.update_status("Search rate limit exceeded")
                if retries < MAX_RETRIES:
                    delay = self.calculate_retry_delay(response, 'search', retries)
                    retry_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                    self.update_status(f"Next search attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    time.sleep(delay)
                    params['retries'] = retries + 1
                    self.action_queue.put(('search', params))
                else:
                    self.update_status("Max retries reached for search")
                    self.stop_processing = True
            else:
                self.update_status("Search failed")
                self.debug_log(f"Non-429 HTTP error: {e}")
                if retries < MAX_RETRIES:
                    retry_time = datetime.datetime.now() + datetime.timedelta(seconds=self.retry_interval)
                    self.update_status(f"Next search attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    time.sleep(self.retry_interval)
                    params['retries'] = retries + 1
                    self.action_queue.put(('search', params))
                else:
                    self.update_status("Max retries reached for search")
                    self.stop_processing = True

        except Exception as e:
            duration = time.time() - start_time
            self.logger.log_call('GET /2/tweets/search/recent', duration, None)
            self.debug_log(f"Unexpected error: {e}")
            self.update_status("Search failed")
            if retries < MAX_RETRIES:
                retry_time = datetime.datetime.now() + datetime.timedelta(seconds=self.retry_interval)
                self.update_status(f"Next search attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(self.retry_interval)
                params['retries'] = retries + 1
                self.action_queue.put(('search', params))
            else:
                self.update_status("Max retries reached for search")
                self.stop_processing = True

    def perform_reply(self, params):
        if not self.client:
            self.client = create_client()
            if not self.client:
                self.update_status("API reconnection failed")
                self.stop_processing = True
                return

        start_time = time.time()
        post_id = params['post_id']
        text = params['text']
        retries = params.get('retries', 0)

        try:
            self.debug_log(f"Attempting reply to post {post_id} (retry attempt {retries + 1}/{MAX_RETRIES})")
            response = self.client.create_tweet(text=text, in_reply_to_tweet_id=post_id)
            duration = time.time() - start_time
            self.logger.log_call('POST /2/tweets', duration, response)
            self.update_status(f"Replied to post {post_id}")

        except tweepy.TooManyRequests as e:
            duration = time.time() - start_time
            self.logger.log_call('POST /2/tweets', duration, None)
            self.debug_log(f"TooManyRequests error: {e}")
            self.update_status("Reply rate limit exceeded")
            if retries < MAX_RETRIES:
                delay = self.calculate_retry_delay(e.response, 'reply', retries)
                retry_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                self.update_status(f"Next reply attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(delay)
                params['retries'] = retries + 1
                self.action_queue.put(('reply', params))
            else:
                self.update_status(f"Max retries reached for reply to post {post_id}")
                self.stop_processing = True

        except tweepy.TweepyException as e:
            duration = time.time() - start_time
            self.logger.log_call('POST /2/tweets', duration, None)
            self.debug_log(f"Tweepy error: {e}")
            self.update_status("Reply failed")
            if retries < MAX_RETRIES:
                retry_time = datetime.datetime.now() + datetime.timedelta(seconds=self.retry_interval)
                self.update_status(f"Next reply attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(self.retry_interval)
                params['retries'] = retries + 1
                self.action_queue.put(('reply', params))
            else:
                self.update_status(f"Max retries reached for reply to post {post_id}")
                self.stop_processing = True

    def perform_like(self, params):
        if not self.client:
            self.client = create_client()
            if not self.client:
                self.update_status("API reconnection failed")
                self.stop_processing = True
                return

        start_time = time.time()
        post_id = params['post_id']
        retries = params.get('retries', 0)

        try:
            self.debug_log(f"Attempting to like post {post_id} (retry attempt {retries + 1}/{MAX_RETRIES})")
            response = self.client.like(post_id)
            duration = time.time() - start_time
            self.logger.log_call('POST /2/users/:id/likes', duration, response)
            self.update_status(f"Liked post {post_id}")

        except tweepy.TooManyRequests as e:
            duration = time.time() - start_time
            self.logger.log_call('POST /2/users/:id/likes', duration, None)
            self.debug_log(f"TooManyRequests error: {e}")
            self.update_status("Like rate limit exceeded")
            if retries < MAX_RETRIES:
                delay = self.calculate_retry_delay(e.response, 'like', retries)
                retry_time = datetime.datetime.now() + datetime.timedelta(seconds=delay)
                self.update_status(f"Next like attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(delay)
                params['retries'] = retries + 1
                self.action_queue.put(('like', params))
            else:
                self.update_status(f"Max retries reached for like on post {post_id}")
                self.stop_processing = True

        except tweepy.TweepyException as e:
            duration = time.time() - start_time
            self.logger.log_call('POST /2/users/:id/likes', duration, None)
            self.debug_log(f"Tweepy error: {e}")
            self.update_status("Like failed")
            if retries < MAX_RETRIES:
                retry_time = datetime.datetime.now() + datetime.timedelta(seconds=self.retry_interval)
                self.update_status(f"Next like attempt: {retry_time.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(self.retry_interval)
                params['retries'] = retries + 1
                self.action_queue.put(('like', params))
            else:
                self.update_status(f"Max retries reached for like on post {post_id}")
                self.stop_processing = True

    def update_search_results(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.post_check_vars.clear()
        
        if self.posts:
            user_dict = {user['id']: user['username'] for user in self.users}
            for i, post in enumerate(self.posts):
                username = user_dict.get(post['author_id'], "Unknown")
                post_frame = ttk.Frame(self.scrollable_frame)
                post_frame.pack(fill="x", pady=2)
                
                check_var = tk.IntVar(value=1)
                checkbox = ttk.Checkbutton(post_frame, variable=check_var)
                checkbox.pack(side="left")
                
                post_label = ttk.Label(
                    post_frame,
                    text=f"@{username}: {post['text']}\n[Posted at: {post['created_at']}]",
                    wraplength=600,
                    justify="left"
                )
                post_label.pack(side="left", fill="x", expand=True)
                
                self.post_check_vars.append((post, check_var))
            
            self.execute_button.config(state="normal")
        else:
            ttk.Label(self.scrollable_frame, text="No posts found.").pack()
        
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_closing(self):
        self.running = False
        self.root.destroy()

# Main execution
if __name__ == "__main__":
    client = create_client()
    if client is None:
        print(f"[{get_timestamp()}] Exiting due to authentication failure.")
    else:
        root = tk.Tk()
        app = xApp(root, client)
        root.mainloop()