setup:
	python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt && cd frontend && npm install
api:
	cd backend && ../.venv/bin/python -m uvicorn app.api.main:app --reload --port 8000
ui:
	cd frontend && npm run dev
test:
	cd backend && ../.venv/bin/python -m pytest -q
evals:
	.venv/bin/python -m evals.run_evals
