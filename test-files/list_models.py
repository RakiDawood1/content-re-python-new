# list_models.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

url = f'https://generativelanguage.googleapis.com/v1/models?key={api_key}'

try:
    response = requests.get(url)
    print(f"Status code: {response.status_code}")
    print(f"Available models: {response.text}")
except Exception as e:
    print(f"Error: {e}")