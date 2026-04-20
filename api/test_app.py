import sys
sys.path.insert(0, ".")
print("Starting API...")
from web.app import app
print(f"App: {app}")
print(f"Routers: {app.routes[:5]}")