# -*- coding: utf-8 -*-
"""Inspect projects DB for document files and sample result_json structure."""

from supabase import create_client
import boto3
import json

PROJECTS_URL = "https://zivbesacbxfmwzervmcy.supabase.co"
PROJECTS_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InppdmJlc2FjYnhmbXd6ZXJ2bWN5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjMyMjgzMDQsImV4cCI6MjA3ODgwNDMwNH0.BMNVvJmlFmm1cEzdWa-kBglm0aHmfuhJOSIo9sQ_6xY"

R2_ENDPOINT_URL = "https://3e34724b322829deab18c812f65cd6df.r2.cloudflarestorage.com"
R2_ACCESS_KEY_ID = "32439d7ed871467929318406f00dc770"
R2_SECRET_ACCESS_KEY = "e94dbd012287939cd2c8db73e5781ece096a8fc4b9ee2591f350793e455e99ae"
R2_BUCKET_NAME = "cloud-aizoomdoc"

projects = create_client(PROJECTS_URL, PROJECTS_ANON_KEY)

# Find one document node
docs = projects.table("tree_nodes").select("*").eq("node_type","document").limit(5).execute()
if not docs.data:
    print("No documents found")
    raise SystemExit(0)

doc = docs.data[0]
print("Document:", doc.get("id"), doc.get("name"))
print("Document keys:", list(doc.keys()))

files = projects.table("node_files").select("*").eq("node_id", doc["id"]).execute()
print("Files:", len(files.data))
for f in files.data:
    print("  -", f.get("file_type"), f.get("r2_key") or f.get("storage_key"))

if files.data:
    print("\nnode_files keys:", list(files.data[0].keys()))

# Pick result_json
result_json = next((f for f in files.data if f.get("file_type") == "result_json"), None)
if not result_json:
    print("No result_json for this document")
    raise SystemExit(0)

key = result_json.get("r2_key") or result_json.get("storage_key")
print("Result JSON key:", key)
print("Result JSON metadata:", result_json.get("metadata"))

s3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto"
)

obj = s3.get_object(Bucket=R2_BUCKET_NAME, Key=key)
data = obj["Body"].read()
print("Downloaded bytes:", len(data))

payload = json.loads(data.decode("utf-8"))
print("Top-level keys:", list(payload.keys())[:20])

# Try to find blocks/images
for k in ["blocks", "images", "pages", "annotations"]:
    if k in payload:
        print(f"Key '{k}' type:", type(payload[k]))
        if isinstance(payload[k], list):
            print("Sample:", payload[k][0] if payload[k] else None)
        elif isinstance(payload[k], dict):
            first_key = next(iter(payload[k].keys()), None)
            print("Sample key:", first_key)
        break

