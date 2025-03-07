import tweepy
import datetime
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import time
import threading

# Constants
WAIT_TIME_SECONDS = 300  # 5 minutes
MAX_POST_LENGTH = 280  # X's character limit
MAX_RETRIES = 6  # Maximum retry attempts for rate limits

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
            access_token_secret=ACCESS_TOKEN_SECRET
        )
        return client
    except Exception as e:
        timestamp = get_timestamp()
        print(f"[{timestamp}] Authentication failed: {e}")
        return None

# Helper function to get current timestamp
def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Options Popup Window
class OptionsWindow:
    def __init__(self, parent, app):
        self.app = app
        self.window = tk.Toplevel(parent)
        self.window.title("Options")
        self.window.geometry("300x150")
        self.window.transient(parent)
        self.window.grab_set()

        content_frame = ttk.Frame(self.window, padding="10")
        content_frame.pack(anchor="nw")

        bold_font = ("TkDefaultFont", 10, "bold")
        search_label = ttk.Label(content_frame, text="Search Options:", font=bold_font)
        search_label.pack(anchor="w", pady=(0, 5))
        self.verified_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(content_frame, text="Search only for posts by verified accounts", variable=self.verified_var).pack(anchor="w")
        self.no_replies_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(content_frame, text="Do not include replies in search", variable=self.no_replies_var).pack(anchor="w")

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
        self.root.title("X Post Search and Reply")

        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Define window sizes
        main_width = 800
        main_height = 800
        status_width = 600
        status_height = 400
        
        # Calculate positions
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

        # Frame for input fields
        input_frame = ttk.Frame(self.root, padding="10")
        input_frame.pack(fill="x")

        # Start time
        ttk.Label(input_frame, text="Start Date/Time (YYYY-MM-DD HH:MM):").grid(row=0, column=0, sticky="w")
        self.start_entry = ttk.Entry(input_frame)
        self.start_entry.grid(row=0, column=1, sticky="ew")
        self.start_entry.insert(0, "2025-03-01 14:30")

        # End time
        ttk.Label(input_frame, text="End Date/Time (YYYY-MM-DD HH:MM):").grid(row=1, column=0, sticky="w")
        self.end_entry = ttk.Entry(input_frame)
        self.end_entry.grid(row=1, column=1, sticky="ew")
        self.end_entry.insert(0, "2025-03-06 23:59")

        # Keywords
        ttk.Label(input_frame, text="Keywords:").grid(row=2, column=0, sticky="w")
        self.keyword_entry = ttk.Entry(input_frame, width=40)
        self.keyword_entry.grid(row=2, column=1, sticky="ew")
        self.keyword_entry.insert(0, "python xai")

        # Search button
        self.search_button = ttk.Button(input_frame, text="Search Posts", command=self.search_posts_thread)
        self.search_button.grid(row=2, column=2, padx=10)

        # Options button
        self.options_button = ttk.Button(input_frame, text="Options", command=self.open_options)
        self.options_button.grid(row=2, column=3, padx=10)

        # Post display frame with scrollbar
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

        # Action frame
        ttk.Label(self.root, text="Actions to Perform:").pack(pady=(10, 0))
        self.action_frame = ttk.Frame(self.root, padding="10")
        self.action_frame.pack(fill="x")

        # Reply action
        self.reply_var = tk.BooleanVar(value=False)
        self.reply_check = ttk.Checkbutton(self.action_frame, text="Reply to posts", variable=self.reply_var, command=self.toggle_reply_text)
        self.reply_check.pack(anchor="w")
        self.reply_text_frame = ttk.Frame(self.action_frame)
        self.reply_text = tk.Text(self.reply_text_frame, height=4, width=100, state="disabled")
        self.reply_text.pack()
        self.reply_text_frame.pack(anchor="w", padx=(20, 0), pady=5)

        # Like action
        self.like_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.action_frame, text="Like posts", variable=self.like_var).pack(anchor="w")

        # Execute button (initially disabled)
        self.execute_button = ttk.Button(self.root, text="Execute Actions", command=self.execute_actions, state="disabled")
        self.execute_button.pack(pady=5)

        # Store posts and their checkbox states
        self.post_check_vars = []

        # Options variables
        self.verified_only = tk.BooleanVar(value=False)
        self.no_replies = tk.BooleanVar(value=False)

    def update_status(self, message):
        self.status_window.update(message)
        self.root.update_idletasks()

    def toggle_reply_text(self):
        state = "normal" if self.reply_var.get() else "disabled"
        self.reply_text.config(state=state)

    def open_options(self):
        options_window = OptionsWindow(self.root, self)
        options_window.verified_var.set(self.verified_only.get())
        options_window.no_replies_var.set(self.no_replies.get())
        self.root.wait_window(options_window.window)
        self.verified_only.set(options_window.verified_var.get())
        self.no_replies.set(options_window.no_replies_var.get())

    def validate_inputs(self):
        try:
            start_time = datetime.datetime.strptime(self.start_entry.get(), "%Y-%m-%d %H:%M").replace(
                tzinfo=datetime.timezone.utc
            ).isoformat()
            end_time = datetime.datetime.strptime(self.end_entry.get(), "%Y-%m-%d %H:%M").replace(
                tzinfo=datetime.timezone.utc
            ).isoformat()
            if datetime.datetime.fromisoformat(end_time) <= datetime.datetime.fromisoformat(start_time):
                raise ValueError("End time must be after start time.")
            keywords = self.keyword_entry.get().strip()
            if not keywords:
                raise ValueError("Keywords are required.")
            return keywords, start_time, end_time
        except ValueError as e:
            self.update_status(f"Input error: {e}")
            return None

    def search_posts(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.post_check_vars.clear()
        self.execute_button.config(state="disabled")
        self.reply_var.set(False)
        self.like_var.set(False)
        self.reply_text.config(state="disabled")
        self.reply_text.delete("1.0", tk.END)

        user_input = self.validate_inputs()
        if user_input is None:
            return

        keywords, start_time, end_time = user_input
        today = datetime.datetime.now(datetime.timezone.utc)
        seven_days_ago = today - datetime.timedelta(days=7)
        if datetime.datetime.fromisoformat(start_time) < seven_days_ago:
            messagebox.showwarning("Date Warning", "Start time is older than 7 days. Free tier only supports recent posts.")

        query = f"{keywords} -is:retweet"
        if self.verified_only.get():
            query += " is:verified"
        if self.no_replies.get():
            query += " -is:reply"

        retries = 0
        while retries < MAX_RETRIES:
            try:
                self.update_status(f"Searching with query: {query}")
                posts = self.client.search_recent_tweets(
                    query=query,
                    start_time=start_time,
                    end_time=end_time,
                    max_results=10,
                    tweet_fields=["created_at"],
                    user_fields=["username"],
                    expansions=["author_id"]
                )
                self.posts = posts.data if posts.data else []
                self.users = posts.includes.get("users", [])
                self.update_status(f"Found {len(self.posts)} posts")
                break
            except tweepy.TooManyRequests as e:
                retries += 1
                self.update_status(f"Rate limit hit: {e}. Waiting {WAIT_TIME_SECONDS//60} minutes...")
                time.sleep(WAIT_TIME_SECONDS)
                if retries == MAX_RETRIES:
                    self.update_status(f"Max retries ({MAX_RETRIES}) reached. Aborting search.")
                    self.posts = []
                    self.users = []
                    return
                self.update_status(f"Retrying search ({retries}/{MAX_RETRIES})...")
            except tweepy.TweepyException as e:
                self.update_status(f"Search failed: {e}")
                return

        if self.posts:
            user_dict = {user.id: user.username for user in self.users}
            for i, post in enumerate(self.posts):
                username = user_dict.get(post.author_id, "Unknown")
                post_frame = ttk.Frame(self.scrollable_frame)
                post_frame.pack(fill="x", pady=2)
                
                check_var = tk.IntVar(value=1)
                checkbox = ttk.Checkbutton(post_frame, variable=check_var)
                checkbox.pack(side="left")
                
                post_label = ttk.Label(
                    post_frame,
                    text=f"@{username}: {post.text}\n[Posted at: {post.created_at}]",
                    wraplength=600,
                    justify="left"
                )
                post_label.pack(side="left", fill="x", expand=True)
                
                self.post_check_vars.append((post, check_var))
            
            self.execute_button.config(state="normal")
        else:
            ttk.Label(self.scrollable_frame, text="No posts found.").pack()

    def search_posts_thread(self):
        self.search_button.config(state="disabled")
        threading.Thread(target=self.search_wrapper, daemon=True).start()

    def search_wrapper(self):
        self.search_posts()
        self.search_button.config(state="normal")

    def execute_actions(self):
        selected_posts = [post for post, var in self.post_check_vars if var.get() == 1]
        if not selected_posts:
            self.update_status("No posts selected for actions.")
            return

        if not (self.reply_var.get() or self.like_var.get()):
            self.update_status("No actions selected.")
            return

        if self.reply_var.get():
            reply_text = self.reply_text.get("1.0", tk.END).strip()
            if not reply_text:
                messagebox.showwarning("Input Error", "Reply text is required when 'Reply to posts' is selected.")
                return
            if len(reply_text) > MAX_POST_LENGTH:
                messagebox.showwarning("Length Error", f"Reply exceeds {MAX_POST_LENGTH} characters ({len(reply_text)}). Shorten it.")
                return

        for post in selected_posts:
            try:
                if self.reply_var.get():
                    self.client.create_tweet(text=reply_text, in_reply_to_tweet_id=post.id)
                    self.update_status(f"Replied to post {post.id}")
                if self.like_var.get():
                    self.client.like(post.id)
                    self.update_status(f"Liked post {post.id}")
            except Exception as e:
                self.update_status(f"Error processing post {post.id}: {e}")
        self.update_status("Actions executed successfully.")
        self.execute_button.config(state="disabled")

# Main execution
if __name__ == "__main__":
    client = create_client()
    if client is None:
        print(f"[{get_timestamp()}] Exiting due to authentication failure.")
    else:
        root = tk.Tk()
        app = xApp(root, client)
        root.mainloop()