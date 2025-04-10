from logger import APICallLogger
from config import RateLimits

class APICallStats:
    def __init__(self, logger: APICallLogger, license_level: str = 'Free'):
        self.logger = logger
        self.license_level = license_level

    def set_license_level(self, level: str):
        self.license_level = level

    def get_avg_duration(self, call_type: str) -> float:
        api_refs = {
            'search': 'GET /2/tweets/search/recent',
            'reply': 'POST /2/tweets',
            'like': 'POST /2/users/:id/likes'
        }
        durations = [log['duration'] for log in self.logger.get_logs()
                     if log['api_ref'] == api_refs[call_type] and log['response'] != "Failed"]
        return sum(durations) / len(durations) if durations else 0.0

    def format_stats(self) -> str:
        output = [f"License Level: {self.license_level}"]
        for call_type in ['search', 'reply', 'like']:
            limit_info = RateLimits.LIMITS[self.license_level][call_type]
            output.append(f"{call_type.capitalize()}:\n"
                          f"  Limit: {limit_info['limit']}/{limit_info['window']}\n"
                          f"  Avg Duration: {self.get_avg_duration(call_type):.2f}s")
        return "\n".join(output)