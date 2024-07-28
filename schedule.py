import requests
import json
import base64
import os
from datetime import datetime
import pytz
from flask import Flask, request, redirect, render_template_string
import logging
import urllib.parse

app = Flask(__name__)

# Zoom OAuth credentials
CLIENT_ID = '_6KMf8b7RJuB10ydU_bKGA'
CLIENT_SECRET = 'HbQRz9vf3hAFeqQXD1uat2biYCTYS4gh'
REDIRECT_URI = 'https://deploymeet.onrender.com/zoom/callback'

TOKEN_FILE = 'zoom_tokens.json'
IST = pytz.timezone('Asia/Kolkata')  # IST Timezone

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper function to load tokens from a file
def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            return json.load(f)
    return {}

# Helper function to save tokens to a file
def save_tokens(tokens):
    with open(TOKEN_FILE, 'w') as f:
        json.dump(tokens, f)

# Step 1: Get Authorization URL
@app.route('/')
def home():
    form_html = '''
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f9;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }
        form {
            background: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }
        label {
            display: block;
            margin: 10px 0 5px;
        }
        input, button {
            width: 100%;
            padding: 10px;
            margin: 5px 0;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        button {
            background: #007bff;
            color: #fff;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background: #0056b3;
        }
    </style>
    <form action="/schedule" method="post">
        <label for="topic">Meeting Topic:</label>
        <input type="text" id="topic" name="topic" required>
        <label for="date">Date (YYYY-MM-DD):</label>
        <input type="date" id="date" name="date" required>
        <label for="time">Time (HH:MM):</label>
        <input type="time" id="time" name="time" required>
        <button type="submit">Schedule Meeting</button>
    </form>
    '''
    return render_template_string(form_html)

@app.route('/schedule', methods=['POST'])
def schedule():
    try:
        topic = request.form['topic']
        date = request.form['date']
        time = request.form['time']
        start_time = f"{date}T{time}:00"
        start_time_ist = datetime.fromisoformat(start_time).replace(tzinfo=IST)
        start_time_utc = start_time_ist.astimezone(pytz.utc).isoformat()
        
        # Validate start_time_utc and topic before using them
        if not start_time_utc or not topic:
            raise ValueError("Start time or topic is missing")
        
        state_param = f"{start_time_utc}#{topic}"
        encoded_state = urllib.parse.quote(state_param)
        logger.info(f"Encoded state parameter for auth URL: {encoded_state}")
        
        auth_url = (
            f"https://zoom.us/oauth/authorize?response_type=code&client_id={CLIENT_ID}&scope=meeting:write:meeting"
            f"&redirect_uri={REDIRECT_URI}&state={encoded_state}"
        )
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        return f"Failed to schedule meeting: {e}"

# Step 2: Exchange Authorization Code for Access Token
@app.route('/zoom/callback')
def callback():
    try:
        code = request.args.get('code')
        encoded_state = request.args.get('state')
        
        # Add logging to debug state
        logger.info(f"Encoded state parameter: {encoded_state}")
        
        # Decode state parameter
        state = urllib.parse.unquote(encoded_state)
        logger.info(f"Decoded state parameter: {state}")
        
        # Split state to get start_time and topic
        if state and '#' in state:
            start_time, topic = state.split('#', 1)  # Only split once to avoid issues with extra #
        else:
            raise ValueError("State parameter is not properly formatted")

        logger.info(f"Authorization code received: {code}")
        logger.info(f"Start time: {start_time}, Topic: {topic}")

        token_url = "https://zoom.us/oauth/token"
        headers = {
            "Authorization": f"Basic {base64.b64encode((CLIENT_ID + ':' + CLIENT_SECRET).encode()).decode()}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI
        }
        response = requests.post(token_url, headers=headers, data=payload)
        response_data = response.json()

        logger.info(f"Token response data: {response_data}")

        if 'access_token' in response_data:
            save_tokens(response_data)
            access_token = response_data.get("access_token")
            join_url = schedule_meeting(access_token, start_time, topic)
            if join_url:
                return redirect(join_url)
            else:
                return "Failed to schedule meeting."
        else:
            logger.error(f"Failed to obtain access token: {response_data}")
            return f"Failed to obtain access token: {response_data}"
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        return f"Failed to process callback: {e}"

# Step 3: Refresh Access Token
def refresh_access_token(refresh_token):
    try:
        token_url = "https://zoom.us/oauth/token"
        headers = {
            "Authorization": f"Basic {base64.b64encode((CLIENT_ID + ':' + CLIENT_SECRET).encode()).decode()}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        response = requests.post(token_url, headers=headers, data=payload)
        response_data = response.json()
        if 'access_token' in response_data:
            save_tokens(response_data)
        return response_data.get("access_token")
    except Exception as e:
        logger.error(f"Error refreshing access token: {e}")
        return None

# Step 4: Schedule a Meeting and Get Join URL
def schedule_meeting(access_token, start_time, topic):
    try:
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        meeting_details = {
            "topic": topic,
            "type": 2,  # Scheduled meeting
            "start_time": start_time,  # Meeting start time in ISO 8601 format
            "duration": 60,  # Duration in minutes
            "timezone": "UTC",
            "agenda": "This is an automated meeting",
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": False,
                "mute_upon_entry": True,
                "watermark": True,
                "use_pmi": False,
                "approval_type": 0,  # Automatically approve
                "registration_type": 1,  # Attendees register once and can attend any of the occurrences
                "audio": "both",  # Both telephony and VoIP
                "auto_recording": "cloud"
            }
        }
        
        user_id = 'me'  # Use 'me' for the authenticated user, or replace with a specific user ID
        response = requests.post(f'https://api.zoom.us/v2/users/{user_id}/meetings', headers=headers, json=meeting_details)
        
        if response.status_code == 201:
            meeting = response.json()
            join_url = meeting.get('join_url')
            return join_url
        else:
            logger.error(f"Failed to schedule meeting: {response.json()}")
            return None
    except Exception as e:
        logger.error(f"Error scheduling meeting: {e}")
        return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
