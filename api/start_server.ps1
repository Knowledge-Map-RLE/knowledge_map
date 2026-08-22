Set-Location "D:\Knowledge_Map\api"
poetry run python -m uvicorn web.app:app --host 0.0.0.0 --port 8000
