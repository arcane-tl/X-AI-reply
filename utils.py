import datetime
import tweepy
import os
from dotenv import load_dotenv

def get_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def create_client():
    try:
        return tweepy.Client(
            bearer_token=os.getenv("BEARER_TOKEN"),
            consumer_key=os.getenv("API_KEY"),
            consumer_secret=os.getenv("API_SECRET"),
            access_token=os.getenv("ACCESS_TOKEN"),
            access_token_secret=os.getenv("ACCESS_TOKEN_SECRET"),
            return_type=dict
        )
    except Exception as e:
        print(f"Authentication failed: {e}")
        return None