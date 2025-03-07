import tweepy
import datetime
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import simpledialog, messagebox
import time

# Constants
WAIT_TIME_SECONDS = 300  # 5 minutes
MAX_TWEET_LENGTH = 280  # X's character limit
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
        print("Authentication successful.")
        return client
    except Exception as e:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Authentication failed: {e}")
        return None

# Helper function to get current timestamp
def get_timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Function to search tweets by keywords and date range with retry on 429
def search_tweets(client, keywords, start_time, end_time, max_results=10):
    query = f"{keywords} -is:retweet"
    print(f"[{get_timestamp()}] Searching with query: {query}, start: {start_time}, end: {end_time}")
    retries = 0
    while retries < MAX_RETRIES:
        try:
            tweets = client.search_recent_tweets(
                query=query,
                start_time=start_time,
                end_time=end_time,
                max_results=max_results,
                tweet_fields=["created_at"],
                user_fields=["username"],
                expansions=["author_id"]
            )
            print(f"[{get_timestamp()}] Search completed successfully.")
            return tweets.data if tweets.data else [], tweets.includes.get("users", [])
        except tweepy.TooManyRequests as e:
            retries += 1
            timestamp = get_timestamp()
            messagebox.showwarning(
                "Rate Limit",
                f"[{timestamp}] 429 Too Many Requests: {e}. Waiting 5 minutes before retrying..."
            )
            print(f"[{timestamp}] Rate limit hit: {e}. Waiting {WAIT_TIME_SECONDS} seconds.")
            time.sleep(WAIT_TIME_SECONDS)
            if retries == MAX_RETRIES:
                print(f"[{get_timestamp()}] Max retries ({MAX_RETRIES}) reached. Aborting search.")
                return [], []
            print(f"[{get_timestamp()}] Retrying search ({retries}/{MAX_RETRIES})...")
        except tweepy.TweepyException as e:
            timestamp = get_timestamp()
            messagebox.showerror("Error", f"[{timestamp}] Search failed: {e}")
            print(f"[{timestamp}] Search error: {e}")
            return [], []

# Function to reply to a tweet
def reply_to_tweet(client, tweet_id, reply_text):
    try:
        client.create_tweet(text=reply_text, in_reply_to_tweet_id=tweet_id)
        print(f"[{get_timestamp()}] Replied to tweet {tweet_id} with: {reply_text}")
    except Exception as e:
        timestamp = get_timestamp()
        print(f"[{timestamp}] Error replying to tweet {tweet_id}: {e}")

# Function to get user input for search parameters
def get_user_input(root):
    start_time_str = simpledialog.askstring(
        "Input",
        "Enter start date and time (YYYY-MM-DD HH:MM, e.g., 2025-03-01 14:30):",
        parent=root
    )
    if not start_time_str:
        messagebox.showwarning("Input Error", "Start time is required.")
        return None

    end_time_str = simpledialog.askstring(
        "Input",
        "Enter end date and time (YYYY-MM-DD HH:MM, e.g., 2025-03-06 23:59):",
        parent=root
    )
    if not end_time_str:
        messagebox.showwarning("Input Error", "End time is required.")
        return None

    keywords = simpledialog.askstring(
        "Input",
        "Enter keywords (e.g., python xai):",
        parent=root
    )
    if not keywords:
        messagebox.showwarning("Input Error", "Keywords are required.")
        return None

    try:
        start_time = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M").replace(
            tzinfo=datetime.timezone.utc
        ).isoformat()
        end_time = datetime.datetime.strptime(end_time_str, "%Y-%m-%d %H:%M").replace(
            tzinfo=datetime.timezone.utc
        ).isoformat()
        
        if datetime.datetime.fromisoformat(end_time) <= datetime.datetime.fromisoformat(start_time):
            raise ValueError("End time must be after start time.")
    except ValueError as e:
        timestamp = get_timestamp()
        messagebox.showerror("Time Error", f"[{timestamp}] Invalid format or logic: {e}. Use YYYY-MM-DD HH:MM.")
        return None

    return keywords, start_time, end_time

# Function to ask if user wants to reply and get reply text with length validation
def prompt_for_reply(root, tweets, users):
    user_dict = {user.id: user.username for user in users}
    tweet_summary = "\n\n".join([
        f"@{user_dict.get(tweet.author_id, 'Unknown')}: {tweet.text}"
        for tweet in tweets
    ])
    
    reply_choice = messagebox.askyesno(
        "Tweets Found",
        f"Found {len(tweets)} tweets:\n\n{tweet_summary}\n\nDo you want to reply to these tweets?"
    )

    if reply_choice:
        while True:
            reply_text = simpledialog.askstring(
                "Reply",
                f"Enter the reply text (max {MAX_TWEET_LENGTH} chars):",
                parent=root
            )
            if not reply_text:
                messagebox.showwarning("Input Error", "Reply text is required.")
                return None
            if len(reply_text) > MAX_TWEET_LENGTH:
                messagebox.showwarning(
                    "Length Error",
                    f"Reply exceeds {MAX_TWEET_LENGTH} characters ({len(reply_text)}). Shorten it."
                )
            else:
                break
        return reply_text
    return None

# Main execution
if __name__ == "__main__":
    client = create_client()
    if client is None:
        print(f"[{get_timestamp()}] Exiting due to authentication failure.")
    else:
        root = tk.Tk()
        root.withdraw()

        user_input = get_user_input(root)
        if user_input is None:
            print(f"[{get_timestamp()}] User canceled or invalid input provided. Exiting.")
        else:
            keywords, start_time, end_time = user_input
            
            today = datetime.datetime.now(datetime.timezone.utc)
            seven_days_ago = today - datetime.timedelta(days=7)
            start_dt = datetime.datetime.fromisoformat(start_time)
            if start_dt < seven_days_ago:
                messagebox.showwarning(
                    "Date Warning",
                    "Start time is older than 7 days. Free tier only supports recent tweets."
                )

            tweets, users = search_tweets(client, keywords, start_time, end_time)
            
            if tweets:
                print(f"[{get_timestamp()}] Found {len(tweets)} tweets:")
                user_dict = {user.id: user.username for user in users}
                for tweet in tweets:
                    username = user_dict.get(tweet.author_id, "Unknown")
                    print(f"@{username}: {tweet.text}")
                    print(f"Posted at: {tweet.created_at}")
                    print("-" * 50)
                
                reply_text = prompt_for_reply(root, tweets, users)
                if reply_text:
                    for tweet in tweets:
                        reply_to_tweet(client, tweet.id, reply_text)
                    print(f"[{get_timestamp()}] Replies posted successfully.")
                else:
                    print(f"[{get_timestamp()}] User chose not to reply. Exiting.")
            else:
                timestamp = get_timestamp()
                messagebox.showinfo("No Results", f"[{timestamp}] No tweets found matching the criteria.")
                print(f"[{timestamp}] No tweets found. Exiting.")

        root.destroy()