# -*- coding: utf-8 -*-
"""Check existing chats in database."""

from supabase import create_client

# Main DB
url = "https://dgfoypolporuxqsvqwel.supabase.co"
key = "sb_publishable_7DTHpsS8LA4BtNRDRXOvLQ_pjvdlOAw"

client = create_client(url, key)

# Get all chats
print("\n=== CHATS (all) ===")
response = client.table("chats").select("id, title, user_id, created_at").order("created_at", desc=True).limit(20).execute()
for chat in response.data:
    user_id = chat.get('user_id', 'NULL')
    title = chat.get('title', 'NO TITLE')
    print(f"  user_id='{user_id}' | title='{title}'")

# Get users
print("\n=== USERS ===")
try:
    response = client.table("users").select("id, username, static_token").execute()
    for user in response.data:
        print(f"  username='{user['username']}' | token='{user.get('static_token', 'N/A')[:30]}...'")
except Exception as e:
    print(f"  Error: {e}")

# Get distinct user_ids in chats
print("\n=== DISTINCT user_ids in chats ===")
response = client.table("chats").select("user_id").execute()
user_ids = set(chat.get('user_id') for chat in response.data)
for uid in user_ids:
    print(f"  '{uid}'")
