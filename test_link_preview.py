"""Test script for link_preview message type handling."""
import requests
import json

# Test link_preview webhook payload
link_preview_payload = {
    "event": {
        "type": "messages",
        "event": "new_message"
    },
    "channel_id": "test_channel",
    "messages": [
        {
            "id": "test_link_preview_msg_123",
            "from": "4915202618514",
            "from_me": False,
            "type": "link_preview",
            "chat_id": "4915202618514@s.whatsapp.net",
            "timestamp": 1700000000,
            "source": "mobile",
            "text": {
                "body": "Check out this cool link: https://example.com"
            },
            "link_preview": {
                "url": "https://example.com",
                "title": "Example Website",
                "description": "An example website"
            }
        }
    ]
}

# Send to local webhook endpoint
url = "http://localhost:8000/webhook/whapi"

print("=" * 80)
print("Testing link_preview message type handling")
print("=" * 80)
print(f"\nSending webhook to: {url}")
print(f"\nPayload:")
print(json.dumps(link_preview_payload, indent=2))
print("\n" + "=" * 80)

try:
    response = requests.post(
        url,
        json=link_preview_payload,
        headers={"Content-Type": "application/json"}
    )

    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Body: {response.json()}")

    if response.status_code == 200:
        print("\n✅ SUCCESS: Webhook accepted!")
        print("\nCheck the worker logs to verify:")
        print("  - No 'Unsupported message type: link_preview' warning")
        print("  - Message processed successfully")
        print("  - Content extracted from text field")
    else:
        print("\n❌ FAILED: Webhook rejected")

except Exception as e:
    print(f"\n❌ ERROR: {e}")

print("\n" + "=" * 80)
