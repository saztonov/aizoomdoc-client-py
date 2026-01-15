# -*- coding: utf-8 -*-
"""Create default_user in database."""

from supabase import create_client
from datetime import datetime

url = "https://dgfoypolporuxqsvqwel.supabase.co"
key = "sb_publishable_7DTHpsS8LA4BtNRDRXOvLQ_pjvdlOAw"

client = create_client(url, key)

# Create default_user
try:
    response = client.table("users").insert({
        "username": "default_user",
        "static_token": "dev-static-token-default-user",
        "status": "active"
    }).execute()
    
    print("Created user:", response.data)
except Exception as e:
    print(f"Error: {e}")

# Verify
print("\n=== USERS after ===")
response = client.table("users").select("id, username, static_token, status").execute()
for user in response.data:
    print(f"  {user['username']} | {user.get('status', 'N/A')}")

