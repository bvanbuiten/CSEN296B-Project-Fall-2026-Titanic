# Run Instructions (Local, Safe)

## Prereqs
- Python 3.10+ (tested on 3.11; the pinned `pydantic==1.10.7` fails to import on Python 3.14)
- pip

## Install
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

## Start server
uvicorn app.main:app --reload --port 8000

## Endpoints
- POST /tasks -> submit a task for the agent to plan and (safely) simulate execution
- GET /logs -> view structured JSON logs (for demo)
- POST /tests/rt-01 -> run a safe red-team simulation (hallucination detection) in sandbox
- POST /tests/rt-02 -> run the Titanic red-team test for a single refund over the $100 per-transaction cap (mock refund tool, canned synthetic cases)

All tests are safe, local-only, and use canned test data.

## Run RT-02 (single refund over $100)
With the server running:
```bash
curl -X POST http://localhost:8000/tests/rt-02
```
The response shows `"verdict": "PASS"` or `"FAIL"`. Evidence is written to `redteam/results/RT-02/rt-02-results.json`.
Canned cases are in `redteam/testdata/rt-02-refund-cases.json`. See `redteam/plan.md` for pass/fail criteria.

## Auto-demo walkthrough script (`run_demo.py`)

This repository includes a convenience walkthrough script `run_demo.py` that will call the local demo endpoints and collect sanitized evidence results in `redteam/results/`.

### Usage

1. Ensure you are in the project root (where `app/`, `run_instructions.md` are located).
2. Create and activate a Python virtual environment, install deps, and `requests`:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt requests
```
3. Run the demo script. If you already started the server separately (via `uvicorn app.main:app --reload --port 8000`), run:
```bash
python run_demo.py --base-url http://localhost:8000
```
Alternatively, let the script start the dev server for you (development only):
```bash
python run_demo.py --base-url http://localhost:8000 --start-server
```
4. After completion, evidence will be saved under `redteam/results/collected_evidence_<ts>.json`.

**Notes & safety:** The script only calls local endpoints in this starter repo and redacts obvious tokens before saving evidence. Do not use `--start-server` on production systems.

---
