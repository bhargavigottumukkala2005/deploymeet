import requests
import json
import base64
import os
from datetime import datetime
import pytz
from flask import Flask, request, redirect, render_template_string

app = Flask(__name__)

# Zoom OAuth credentials
CLIENT_ID = '_6KMf8b7RJuB10ydU_bKGA'
CLIENT_SECRET = 'HbQRz9vf3hAFeqQXD1uat2biYCTYS4gh'
REDIRECT_URI = 'https://deploymeet.onrender.com/zoom/callback'

TOKEN_FILE = 'zoom_tokens.json'
IST = pytz.timezone('Asia/Kolkata')  # IST Timezone

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
    <form action="/schedule" method="post">
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
    date = request.form['date']
    time = request.form['time']
    start_time = f"{date}T{time}:00"
    start_time_ist = datetime.fromisoformat(start_time).replace(tzinfo=IST)
    start_time_utc = start_time_ist.astimezone(pytz.utc).isoformat()
    auth_url = (
        f"https://zoom.us/oauth/authorize?response_type=code&client_id={CLIENT_ID}&scope=meeting:write:meeting"
        f"&redirect_uri={REDIRECT_URI}&state={start_time_utc}"
    )
    return redirect(auth_url)

# Step 2: Exchange Authorization Code for Access Token
@app.route('/zoom/callback')
def callback():
    code = request.args.get('code')
    start_time = request.args.get('state')  # Retrieve the start_time from the state parameter
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
    if 'access_token' in response_data:
        save_tokens(response_data)
        access_token = response_data.get("access_token")
        join_url = schedule_meeting(access_token, start_time)
        if join_url:
            return redirect(join_url)
        else:
            return "Failed to schedule meeting."
    else:
        return "Failed to obtain access token."

# Step 3: Refresh Access Token
def refresh_access_token(refresh_token):
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

# Step 4: Schedule a Meeting and Get Join URL
def schedule_meeting(access_token, start_time):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    meeting_details = {
        "topic": "Automated Meeting",
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
        return None

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
