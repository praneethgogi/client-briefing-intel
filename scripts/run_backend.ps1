# Starts the API on http://127.0.0.1:8000  (docs at /docs)
Push-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --port 8000
Pop-Location
