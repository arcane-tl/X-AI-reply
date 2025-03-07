import tweepy
import datetime
from dotenv import load_dotenv
import os
import tkinter as tk
from tkinter import simpledialog, messagebox

# Load environment variables from cred.env
load_dotenv("cred.env")

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
BEARER_TOKEN = os.getenv("BEARER_TOKEN")

if not all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET, BEARER_TOKEN]):
    raise ValueError("One or more environment variables are missing. Check your cred.env file.")

# Authenticate with X API v2 (commented out for mock testing)
# client = tweepy.Client(
#     bearer_token=BEARER_TOKEN,
#     consumer_key=API_KEY,
#     consumer_secret=API_SECRET,
#     access_token=ACCESS_TOKEN,
#     access_token_secret=ACCESS_TOKEN_SECRET
# )
# print("Authentication successful.")

# Mock search function (replace real API call)
def search_tweets(keywords, start_time, end_time):
    print(f"Mock search with query: {keywords}, start: {start_time}, end: {end_time}")
    # Simulate some tweet data
    mock_tweets = [
        type('Tweet', (), {
            'id': 1,
            'text': f"Mock tweet about {keywords} - 1",
            'author_id': 1,
            'created_at': start_time
        })(),
        type('Tweet', (), {
            'id': 2,
            'text': f"Mock tweet about {keywords} - 2",
            'author_id': 2,
            'created_at': end_time
        })()
    ]
    mock_users = [
        type('User', (), {'id': 1, 'username': 'mockuser1'})(),
        type('User', (), {'id': 2, 'username': 'mockuser2'})()
    ]
    return mock_tweets, mock_users

# Function to reply to a tweet (mocked for testing)
def reply_to_tweet(tweet_id, reply_text):
    print(f"[Mock] Would reply to tweet {tweet_id} with: {reply_text}")

# Function to get user input for search parameters
def get_user_input():
    root = tk.Tk()
    root.withdraw()

    start_time_str = simpledialog.askstring(
        "Input",
        "Enter start date and time (YYYY-MM-DD HH:MM, e.g., 2025-03-01 14:30):",
        parent=root
    )
    if not start_time_str:
        messagebox.showwarning("Input Error", "Start time is required.")
        root.destroy()
        return None

    end_time_str = simpledialog.askstring(
        "Input",
        "Enter end date and time (YYYY-MM-DD HH:MM, e.g., 2025-03-06 23:59):",
        parent=root
    )
    if not end_time_str:
        messagebox.showwarning("Input Error", "End time is required.")
        root.destroy()
        return None

    keywords = simpledialog.askstring(
        "Input",
        "Enter keywords (e.g., python xai):",
        parent=root
    )
    if not keywords:
        messagebox.showwarning("Input Error", "Keywords are required.")
        root.destroy()
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
        messagebox.showerror("Time Error", f"Invalid format or logic: {e}. Use YYYY-MM-DD HH:MM.")
        root.destroy()
        return None

    root.destroy()
    return keywords, start_time, end_time

# Function to ask if user wants to reply and get reply text
def prompt_for_reply(tweets, users):
    root = tk.Tk()
    root.withdraw()

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
        reply_text = simpledialog.askstring(
            "Reply",
            "Enter the reply text:",
            parent=root
        )
        if not reply_text:
            messagebox.showwarning("Input Error", "Reply text is required.")
            root.destroy()
            return None
        root.destroy()
        return reply_text
    else:
        root.destroy()
        return None

# Main execution
if __name__ == "__main__":
    user_input = get_user_input()
    if user_input is None:
        print("User canceled or invalid input provided.")
        exit()

    keywords, start_time, end_time = user_input
    
    today = datetime.datetime.now(datetime.timezone.utc)
    seven_days_ago = today - datetime.timedelta(days=7)
    start_dt = datetime.datetime.fromisoformat(start_time)
    if start_dt < seven_days_ago:
        messagebox.showwarning(
            "Date Warning",
            "Start time is older than 7 days. Free tier only supports recent tweets."
        )

    tweets, users = search_tweets(keywords, start_time, end_time)
    
    if tweets:
        print(f"Found {len(tweets)} tweets:")
        user_dict = {user.id: user.username for user in users}
        for tweet in tweets:
            username = user_dict.get(tweet.author_id, "Unknown")
            print(f"@{username}: {tweet.text}")
            print(f"Posted at: {tweet.created_at}")
            print("-" * 50)
        
        reply_text = prompt_for_reply(tweets, users)
        if reply_text:
            for tweet in tweets:
                reply_to_tweet(tweet.id, reply_text)
            print("Replies posted successfully (mocked).")
        else:
            print("User chose not to reply. Exiting.")
            exit()
    else:
        messagebox.showinfo("No Results", "No tweets found matching the criteria.")
        print("No tweets found. Exiting.")
        exit()