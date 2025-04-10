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
        'Free': {'search': {'limit': 1, 'window': '15m'}, 'reply': {'limit': 17, 'window': '24h'}, 'like': {'limit': 1, 'window': '15m'}},
        'Basic': {'search': {'limit': 60, 'window': '15m'}, 'reply': {'limit': 100, 'window': '24h'}, 'like': {'limit': 200, 'window': '24h'}},
        'Pro': {'search': {'limit': 300, 'window': '15m'}, 'reply': {'limit': 100, 'window': '15m'}, 'like': {'limit': 1000, 'window': '24h'}}
    }