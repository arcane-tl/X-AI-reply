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
        self.stats = APICallStats(self.logger, self.license_level.get())
        self.action_queue = Queue()
        self.running = True
        self.stop_processing_event = threading.Event()
        self.root.title("X Post Search and Reply")
        self.posts = []
        self.users = []
        self.status_window = None
        self.setup_gui()
        self.processor_thread = threading.Thread(target=self.process_action_queue, daemon=True)
        self.processor_thread.start()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_gui(self):
        screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        main_x, main_y = 50, (screen_height - GUIConfig.MAIN_SIZE[1]) // 2
        status_x, status_y = main_x + GUIConfig.MAIN_SIZE[0] + 10, main_y
        if status_x + GUIConfig.STATUS_SIZE[0] > screen_width:
            status_x = screen_width - GUIConfig.STATUS_SIZE[0] - 50
        if main_y + GUIConfig.MAIN_SIZE[1] > screen_height:
            main_y = status_y = 50

        self.root.geometry(f"{GUIConfig.MAIN_SIZE[0]}x{GUIConfig.MAIN_SIZE[1]}+{main_x}+{main_y}")
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

        self.status_window = StatusWindow(self.root, status_x, status_y)
        self.update_status("Application started.")

        self.root.lift()
        self.root.update_idletasks()
        self.root.update()
        self.status_window.window.lift()
        self.status_window.window.update_idletasks()
        self.status_window.window.update()

    def _setup_input_frame(self, frame: ttk.Frame):
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
        defaults = {'license_level': 'Free', 'verified_only': False, 'no_replies': False, 'retry_interval': 300, 'debug_mode': False}
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
        logger.info(message)
        if self.status_window:
            self.root.after(0, lambda: self.status_window.update(message))

    def debug_log(self, message: str):
        if self.debug_mode.get():
            logger.debug(message)
            self.update_status(f"[DEBUG] {message}")

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
            self.debug_log(f"Executing search: {query}")
            response, success = self.execute_api_call(search_call, 'GET /2/tweets/search/recent')
            response.raise_for_status()
            posts = response.json()
            self.posts = posts.get('data', [])
            self.users = posts.get('includes', {}).get("users", [])
            self.update_status(f"Search completed. Found {len(self.posts)} posts")
            self.root.after(0, self.update_search_results)
        except requests.exceptions.HTTPError as e:
            self.handle_retry('search', params, e.response, e, 'GET /2/tweets/search/recent', start_time)
        except Exception as e:
            self.handle_retry('search', params, None, e, 'GET /2/tweets/search/recent', start_time)

    def perform_reply(self, params):
        if not self.ensure_client():
            return
        start_time = time.time()
        def reply_call():
            return self.client.create_tweet(text=params['text'], in_reply_to_tweet_id=params['post_id'])
        try:
            self.debug_log(f"Replying to post {params['post_id']}")
            response, success = self.execute_api_call(reply_call, 'POST /2/tweets')
            self.update_status(f"Replied to post {params['post_id']}")
        except Exception as e:
            self.handle_retry('reply', params, getattr(e, 'response', None), e, 'POST /2/tweets', start_time)

    def perform_like(self, params):
        if not self.ensure_client():
            return
        start_time = time.time()
        def like_call():
            return self.client.like(params['post_id'])
        try:
            self.debug_log(f"Liking post {params['post_id']}")
            response, success = self.execute_api_call(like_call, 'POST /2/users/:id/likes')
            self.update_status(f"Liked post {params['post_id']}")
        except Exception as e:
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
        self.running = False
        self.root.destroy()

    def calculate_retry_delay(self, response, call_type: str, retries: int):
        return self.retry_interval

    def handle_retry(self, action_type: str, params, response, exception, call_ref: str, start_time: float):
        duration = time.time() - start_time
        self.logger.log_call(call_ref, duration, None)
        retries = params.get('retries', 0)
        if retries >= APIConfig.MAX_RETRIES:
            self.update_status(f"Max retries reached for {action_type}")
            return False
        time.sleep(self.calculate_retry_delay(response, action_type, retries))
        params['retries'] = retries + 1
        self.action_queue.put((action_type, params))
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

if __name__ == "__main__":
    client = create_client()
    if client is None:
        logger.error("Exiting due to authentication failure.")
    else:
        root = tk.Tk()
        app = xApp(root, client)
        root.mainloop()