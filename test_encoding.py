# -*- coding: utf-8 -*-
"""Test encoding of chat titles from server."""

from aizoomdoc_client import AIZoomDocClient

client = AIZoomDocClient(
    server_url='http://localhost:8000', 
    static_token='dev-static-token-test-67890'
)
client.authenticate()

chats = client.list_chats()
for c in chats:
    title = c.title
    print(f"Original title: {title}")
    print(f"Title repr: {repr(title)}")
    print(f"Title bytes (utf-8): {title.encode('utf-8')}")
    
    # Try to fix
    try:
        fixed = title.encode('cp1251').decode('utf-8')
        print(f"Fixed (cp1251->utf8): {fixed}")
    except Exception as e:
        print(f"cp1251->utf8 failed: {e}")
    
    try:
        fixed = title.encode('latin-1').decode('utf-8')
        print(f"Fixed (latin1->utf8): {fixed}")
    except Exception as e:
        print(f"latin1->utf8 failed: {e}")
    
    print("-" * 50)


