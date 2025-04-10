import json
import os
from typing import Any

LOG_FILE = "api_call_log.json"

class APICallLogger:
    def __init__(self):
        self.logs = []
        self.load_logs()

    def log_call(self, api_ref: str, duration: float, response: Any):
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

    def get_logs(self) -> list:
        return self.logs