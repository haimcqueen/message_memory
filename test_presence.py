"""Test script for sending typing presence."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from workers.presence import send_presence

def test_typing_presence():
    """Test sending typing presence to your WhatsApp."""
    # Your chat ID
    chat_id = "4915202618514@s.whatsapp.net"

    print(f"Sending typing presence to {chat_id}...")

    try:
        success = send_presence(chat_id, presence="typing", delay=10)

        if success:
            print("✓ Typing presence sent successfully!")
            print("Check your WhatsApp - you should see 'typing...' for 10 seconds")
        else:
            print("✗ Failed to send typing presence")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_typing_presence()
