# Run Instructions (Local, Safe)

## Prereqs
- Python 3.11. Python 3.14 is not supported by some dependencies.
- pip
- Internet the first time only: to install packages and download the vector database's small embedding model (about 80 MB).

## Install
```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Optional: use the real model (Claude Haiku 5.5)
```bash
cp .env.example .env
# edit .env and replace PASTE_YOUR_KEY_HERE with the Anthropic API key
```
- `.env` is in `.gitignore`. Never commit the key, and never run `git add .`; add files by name.
- Without a key, Titanic runs an offline stand-in model that follows fixed rules through the same policy gate.

## Start server
```bash
uvicorn app.main:app --port 8000
```
Open http://localhost:8000. The customer and supervisor sign-ins are in `docs/USER_GUIDE.md`. Demo data is created in `data/runtime/` on first start; git ignores that folder.

## Endpoints
- GET  / , /customer , /supervisor : browser UI
- /api/... : the API behind the UI (see `app/titanic/api.py`)
- GET  /health : health check
- POST /tasks : starter demo: submit a task for the agent to plan and simulate
- GET  /logs : starter demo: structured JSON logs
- POST /tests/rt-01 : starter red-team simulation (hallucination detection)
- POST /tests/rt-02 : single refund over $100 (mock refund tool, canned synthetic cases)
- POST /tests/rt-03 : direct prompt injection at intake (needs the API key)
- POST /tests/rt-04 : indirect prompt injection through records (needs the API key)
- POST /tests/rt-05 : another customer's records (sensitive information disclosure)
- POST /tests/rt-06 : exceed the $500 weekly refund limit
- POST /tests/rt-07 : email misdirection
- POST /tests/rt-08 : action after revocation

All tests are safe, local-only, and use canned synthetic data. Each Titanic test runs in its own throwaway sandbox.

## Run the red-team tests
With the server running:
```bash
for t in rt-02 rt-05 rt-06 rt-07 rt-08; do curl -X POST http://localhost:8000/tests/$t; echo; done
```
- **Output:** each response shows `"verdict": "PASS"` or `"FAIL"`.
- **Evidence:** each test writes its log to `redteam/results/RT-0X/rt-0X-results.json`.
- **Supervisor portal:** the **Red-team tests** panel runs the same tests.
- **RT-03 and RT-04:** with the key set, run them the same way. Without a key they return `NOT RUN`. To check their harness offline, add `?dry_run=true`; nothing is saved.
- **Negative controls:** `python redteam/negative_controls.py` proves each test fails when its control is switched off. Results go to `redteam/results/negative-controls.json`.

Test definitions and pass/fail criteria: `redteam/plan.md`.

## Auto-demo walkthrough script (`run_demo.py`)

This repository includes a convenience walkthrough script `run_demo.py` that will call the local demo endpoints and collect sanitized evidence results in `redteam/results/`.

### Usage

1. Ensure you are in the project root (where `app/`, `run_instructions.md` are located).
2. Create and activate a Python virtual environment and install dependencies (see Install above).
3. Run the demo script. If you already started the server separately (via `uvicorn app.main:app --port 8000`), run:
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
