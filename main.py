import tweepy
import datetime
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading

# Constants
WAIT_TIME_SECONDS = 300  # 5 minutes
MAX_POST_LENGTH = 280  # X's character limit (renamed for consistency)
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

# GUI Application Class
class TwitterApp:
    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.root.title("X Post Search and Reply")
        self.root.geometry("800x800")

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
        self.keyword_entry = ttk.Entry(input_frame, width=40)  # Doubled size (default is ~20)
        self.keyword_entry.grid(row=2, column=1, sticky="ew")
        self.keyword_entry.insert(0, "python xai")

        # Search button (aligned with keywords)
        self.search_button = ttk.Button(input_frame, text="Search Posts", command=self.search_posts_thread)
        self.search_button.grid(row=2, column=2, padx=10)

        # Post display frame with scrollbar
        ttk.Label(self.root, text="Found Posts (uncheck to exclude from replies):").pack()
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

        # Reply text
        ttk.Label(self.root, text=f"Reply Text (max {MAX_POST_LENGTH} chars):").pack()
        self.reply_text = tk.Text(self.root, height=4, width=100)
        self.reply_text.pack(pady=5)

        # Reply button (initially disabled)
        self.reply_button = ttk.Button(self.root, text="Submit Replies", command=self.submit_replies, state="disabled")
        self.reply_button.pack(pady=5)

        # Status label
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(self.root, textvariable=self.status_var)
        self.status_label.pack(pady=5)

        # Store posts and their checkbox states
        self.post_check_vars = []  # List of (post, IntVar) tuples

    def update_status(self, message):
        self.status_var.set(f"[{get_timestamp()}] {message}")
        self.root.update_idletasks()

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
        # Clear previous posts
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.post_check_vars.clear()
        self.reply_button.config(state="disabled")

        user_input = self.validate_inputs()
        if user_input is None:
            return

        keywords, start_time, end_time = user_input
        today = datetime.datetime.now(datetime.timezone.utc)
        seven_days_ago = today - datetime.timedelta(days=7)
        if datetime.datetime.fromisoformat(start_time) < seven_days_ago:
            messagebox.showwarning("Date Warning", "Start time is older than 7 days. Free tier only supports recent posts.")

        retries = 0
        while retries < MAX_RETRIES:
            try:
                self.update_status(f"Searching with query: {keywords} -is:retweet")
                posts = self.client.search_recent_tweets(
                    query=f"{keywords} -is:retweet",
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
                
                # Checkbox
                check_var = tk.IntVar(value=1)  # Checked by default
                checkbox = ttk.Checkbutton(post_frame, variable=check_var)
                checkbox.pack(side="left")
                
                # Post text
                post_label = ttk.Label(
                    post_frame,
                    text=f"@{username}: {post.text}\n[Posted at: {post.created_at}]",
                    wraplength=600,
                    justify="left"
                )
                post_label.pack(side="left", fill="x", expand=True)
                
                self.post_check_vars.append((post, check_var))
            
            self.reply_button.config(state="normal")
        else:
            ttk.Label(self.scrollable_frame, text="No posts found.").pack()

    def search_posts_thread(self):
        self.search_button.config(state="disabled")
        threading.Thread(target=self.search_wrapper, daemon=True).start()

    def search_wrapper(self):
        self.search_posts()
        self.search_button.config(state="normal")

    def submit_replies(self):
        reply_text = self.reply_text.get("1.0", tk.END).strip()
        if not reply_text:
            messagebox.showwarning("Input Error", "Reply text is required.")
            return
        if len(reply_text) > MAX_POST_LENGTH:
            messagebox.showwarning("Length Error", f"Reply exceeds {MAX_POST_LENGTH} characters ({len(reply_text)}). Shorten it.")
            return

        selected_posts = [post for post, var in self.post_check_vars if var.get() == 1]
        if not selected_posts:
            self.update_status("No posts selected for reply.")
            return

        for post in selected_posts:
            try:
                self.client.create_tweet(text=reply_text, in_reply_to_tweet_id=post.id)
                self.update_status(f"Replied to post {post.id}")
            except Exception as e:
                self.update_status(f"Error replying to post {post.id}: {e}")
        self.update_status("Replies posted successfully.")
        self.reply_button.config(state="disabled")

# Main execution
if __name__ == "__main__":
    client = create_client()
    if client is None:
        print(f"[{get_timestamp()}] Exiting due to authentication failure.")
    else:
        root = tk.Tk()
        app = TwitterApp(root, client)
        root.mainloop()