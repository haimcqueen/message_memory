import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

user_id = "fb86dc17-f4c6-43e1-bad7-2cf1b7dcdea8"

# Check memories table
print("=== Memories for user ===")
response = supabase.table("memories").select("*").eq("user_id", user_id).execute()
print(f"Found {len(response.data)} memories:")
for memory in response.data:
    print(f"  - {memory.get('content')}")

print("\n=== Recent messages for user ===")
# Check messages table
msg_response = supabase.table("messages").select("content, type, origin").eq("user_id", user_id).order("message_sent_at", desc=True).limit(10).execute()
print(f"Found {len(msg_response.data)} recent messages:")
for msg in msg_response.data:
    print(f"  [{msg.get('origin')}] {msg.get('type')}: {msg.get('content')[:100]}")
