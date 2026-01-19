# -*- coding: utf-8 -*-
"""Migrate old chats from default_user to test_user."""

from supabase import create_client

url = "https://dgfoypolporuxqsvqwel.supabase.co"
key = "sb_publishable_7DTHpsS8LA4BtNRDRXOvLQ_pjvdlOAw"

client = create_client(url, key)

# Update all chats with user_id='default_user' to 'test_user'
print("Migrating chats from 'default_user' to 'test_user'...")

response = client.table("chats").update({
    "user_id": "test_user"
}).eq("user_id", "default_user").execute()

print(f"Updated {len(response.data)} chats")

# Verify
print("\n=== CHATS after migration ===")
response = client.table("chats").select("id, title, user_id").limit(5).execute()
for chat in response.data:
    print(f"  user_id='{chat['user_id']}' | title='{chat['title'][:50]}...'")


