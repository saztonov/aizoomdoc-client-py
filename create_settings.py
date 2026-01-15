# -*- coding: utf-8 -*-
"""Create settings for default_user."""

from supabase import create_client

url = "https://dgfoypolporuxqsvqwel.supabase.co"
key = "sb_publishable_7DTHpsS8LA4BtNRDRXOvLQ_pjvdlOAw"

client = create_client(url, key)

# Get default_user id
response = client.table("users").select("id").eq("username", "default_user").execute()
if not response.data:
    print("User not found!")
    exit(1)

user_id = response.data[0]['id']
print(f"User ID: {user_id}")

# Check if settings exist
response = client.table("settings").select("*").eq("user_id", user_id).execute()
if response.data:
    print("Settings already exist:", response.data)
else:
    # Create settings
    response = client.table("settings").insert({
        "user_id": user_id,
        "model_profile": "simple",
        "page_settings": {}
    }).execute()
    print("Created settings:", response.data)

