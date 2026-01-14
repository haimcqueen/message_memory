import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Get API key from env
api_key = os.getenv("N8N_WEBHOOK_API_KEY")

url = "https://web-production-aa894.up.railway.app/api/v1/memory/search"

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "user_id": "fb86dc17-f4c6-43e1-bad7-2cf1b7dcdea8",
    "query": "not wearing makeup"
}

print(f"Making request to: {url}")
print(f"Payload: {payload}\n")

response = requests.post(url, json=payload, headers=headers)

print(f"Status: {response.status_code}")
print(f"Response:\n{response.json()}")
