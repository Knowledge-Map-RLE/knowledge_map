import urllib.request
import json
import sys

url = "http://localhost:8000/api/patterns/global-linguistic-graph?lexical_limit=100&action_limit=100&edge_limit=100&auto_layout=false"

try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())
        print(f"Success: {len(data.get('nodes', []))} nodes, {len(data.get('edges', []))} edges")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    body = e.read().decode()
    print(f"Response: {body}")
except Exception as e:
    print(f"Exception: {e}")
