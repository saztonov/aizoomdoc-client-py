# -*- coding: utf-8 -*-
"""Check how images are stored in chat messages."""

from supabase import create_client

url = "https://dgfoypolporuxqsvqwel.supabase.co"
key = "sb_publishable_7DTHpsS8LA4BtNRDRXOvLQ_pjvdlOAw"

client = create_client(url, key)

# Get a chat with messages
print("=== SAMPLE CHAT MESSAGES ===")
response = client.table("chat_messages").select("id, chat_id, role, content, message_type").limit(5).execute()
for msg in response.data:
    content = msg['content'][:100] if msg['content'] else 'NULL'
    print(f"  role={msg['role']} | type={msg.get('message_type')} | content={content}...")

# Check chat_images table
print("\n=== CHAT_IMAGES ===")
response = client.table("chat_images").select("*").limit(5).execute()
for img in response.data:
    print(f"  message_id={img.get('message_id')} | file_id={img.get('file_id')} | type={img.get('image_type')}")

# Check message_attachments table
print("\n=== MESSAGE_ATTACHMENTS ===")
response = client.table("message_attachments").select("*").limit(5).execute()
for att in response.data:
    print(f"  message_id={att.get('message_id')} | file_id={att.get('file_id')}")

# Check storage_files
print("\n=== STORAGE_FILES (sample) ===")
response = client.table("storage_files").select("id, filename, source_type, storage_path, external_url").limit(5).execute()
for f in response.data:
    print(f"  id={str(f['id'])[:8]}... | type={f.get('source_type')} | path={f.get('storage_path', 'N/A')[:50] if f.get('storage_path') else 'N/A'}")


