# X Post Search and Reply

A Python-based desktop application built with `tweepy` and `tkinter` to search for posts on X (Twitter), reply to them, and like them, with a graphical user interface (GUI). The app supports rate limit handling, customizable search options, and detailed logging for API interactions.

## Features

- **Search Posts**: Search for recent X posts by keywords, date range, and filters (e.g., verified accounts only, exclude replies).
- **Reply to Posts**: Post replies to selected search results with customizable text.
- **Like Posts**: Like selected posts from search results.
- **Rate Limit Management**: Automatically retries API calls upon hitting rate limits, with configurable retry intervals.
- **GUI Interface**: User-friendly interface built with `tkinter` for easy interaction.
- **Statistics Tracking**: View API call statistics (e.g., average duration) based on your license level.
- **Logging**: Detailed logs of API calls stored in `api_call_log.json`.
- **Configurable Options**: Customize search filters, license level, and debug mode via an options menu.

## Prerequisites

- Python 3.7+
- X (Twitter) API credentials (Free, Basic, or Pro tier)
- Required Python packages (listed in [Installation](#installation))

## Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/x-post-search-reply.git
   cd x-post-search-reply

2. **Set Up a Virtual Environment (optional but recommended)**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate

3. **Install Dependencies**:
   ```bash
   pip install tweepy requests python-dotenv tkinter

4. **Configure API Credentials**:
- Create a file named cred.env in the project root directory.
- Add your X API credentials in the following format:
   ```bash
   API_KEY=your_api_key
   API_SECRET=your_api_secret
   ACCESS_TOKEN=your_access_token
   ACCESS_TOKEN_SECRET=your_access_token_secret
   BEARER_TOKEN=your_bearer_token
- Obtain these credentials from the X Developer Portal (https://developer.twitter.com/).

## Usage

### Running the Application

1. **Start the App**:
   - Run the application from the command line:
     ```bash
     python main.py
     ```
   - Replace `main.py` with the actual filename if it differs.

### Main Window

2. **Interacting with the Main Interface**:
   - **Search Inputs**:
     - Enter keywords to search for (e.g., "python xai").
     - Specify a start date/time (format: `YYYY-MM-DD HH:MM`).
     - Specify an end date/time (format: `YYYY-MM-DD HH:MM`).
   - **Search Button**:
     - Click "Search Posts" to retrieve matching posts from X.
   - **Found Posts**:
     - View results in a scrollable list.
     - Uncheck posts to exclude them from subsequent actions.
   - **Actions**:
     - Check "Reply to posts" and/or "Like posts" to select actions.
     - Click "Execute Actions" to perform the selected actions on checked posts.

### Options Window

3. **Customizing Settings**:
   - Access via the "Options" button in the main window.
   - Configure the following:
     - **Search Filters**: Toggle "Search only for verified accounts" and "Exclude replies in search".
     - **API License Level**: Select your tier (Free, Basic, Pro).
     - **Retry Interval**: Set the fallback retry delay (in minutes).
     - **Debug Mode**: Enable/disable detailed logging.

### Status Log

4. **Monitoring Activity**:
   - A separate window displays real-time logs.
   - Shows updates on actions, API call statuses, and errors.

### Statistics

5. **Viewing API Stats**:
   - Click "Show Stats" in the main window.
   - Displays API call statistics (e.g., average duration) based on your license level.

## Configuration

### API License Levels

- **Supported Tiers**: The app supports three X API tiers with predefined rate limits:
  - **Free**:
    - Searches: 1 per 15 minutes
    - Replies: 17 per 24 hours
    - Likes: 1 per 15 minutes
  - **Basic**:
    - Searches: 60 per 15 minutes
    - Replies: 100 per 24 hours
    - Likes: 200 per 24 hours
  - **Pro**:
    - Searches: 300 per 15 minutes
    - Replies: 100 per 15 minutes
    - Likes: 1000 per 24 hours

### User Options

- **Storage**: Options are saved in `user_options.json`.
- **Available Settings**:
  - **`license_level`**:
    - Description: Sets your API tier.
    - Default: `"Free"`.
    - Options: `"Free"`, `"Basic"`, `"Pro"`.
  - **`verified_only`**:
    - Description: Limits searches to verified accounts only.
    - Default: `False`.
    - Options: `True`, `False`.
  - **`no_replies`**:
    - Description: Excludes replies from search results.
    - Default: `False`.
    - Options: `True`, `False`.
  - **`retry_interval`**:
    - Description: Fallback retry delay for API calls (in minutes).
    - Default: `5`.
    - Options: `5`, `15`, `30`, `60`.
  - **`debug_mode`**:
    - Description: Enables detailed debug logging.
    - Default: `False`.
    - Options: `True`, `False`.

### Logging

- **Log File**: API call logs are stored in `api_call_log.json`.
- **Details Captured**:
  - API reference (e.g., endpoint called).
  - Timestamp of the call.
  - Duration of the call.
  - Response status (success or failure).

## Rate Limit Handling

- The app automatically retries API calls when rate limits are hit (up to 6 retries).
- Retry delays are calculated based on:
  - **`x-rate-limit-reset`** or **`x-user-limit-24hour-reset`** headers (if available).
  - Fallback to 15-minute or 24-hour windows based on your license level and action type.

## Troubleshooting

- **Authentication Failure**:
  - Ensure all credentials in `cred.env` are correct and match your API tier.
- **No Posts Found**:
  - Check your search query, date range, and API rate limits.
- **GUI Issues**:
  - Verify `tkinter` is installed and compatible with your Python version.
- **Rate Limit Errors**:
  - Adjust your license level in options or wait for the reset period.

## Contributing

1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature
3. Commit your changes:
   ```bash
   git commit -m "Add your feature"
4. Push to the branch:
   ```bash
   git push origin feature/your-feature
5. Open a pull request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments
- Built with Tweepy for X API integration.
- Uses tkinter for the GUI.