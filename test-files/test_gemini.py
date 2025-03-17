# test_gemini.py
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key
api_key = os.environ.get("GEMINI_API_KEY")
print(f"API key found: {'Yes' if api_key else 'No'}")

# Test request to Gemini API - updated URL and model name
url = 'https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent'

payload = {
    "contents": [{
        "parts": [{
            "text": "Hello, can you respond with a simple 'Hello World'?"
        }]
    }]
}
headers = {
    'Content-Type': 'application/json',
    'x-goog-api-key': api_key
}

try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")