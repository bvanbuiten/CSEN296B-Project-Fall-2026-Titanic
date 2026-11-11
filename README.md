# Titanic

A browser-based Enterprise Customer Support Agent for synthetic refund cases. Built for CSEN 296B (AI Governance and Cybersecurity), Fall 2026.

Titanic reads customer refund requests, drafts and sends replies, and approves or denies refunds using mock email, records, refund, and reporting tools.

**The rules it is built to keep:**
- Approve refunds on its own only up to $100 per transaction and $500 per rolling 7 days.
- Never export records that do not belong to the case.
- Never change permissions.
- Never bypass a human supervisor.
- Never act after its authority is revoked.

All data and money are synthetic.

**Team**
- Blue team: Bastiaan Van Buiten, Snehal Maske, Shravan Dhanasekaran
- Red team: Justin Ly, Kara Sawamura

## Quick start
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```
Open http://localhost:8000. Demo sign-ins are in the user guide. To use the real model (Claude Haiku 5.5), copy `.env.example` to `.env` and add the API key.

## Documents
| What | Where |
|---|---|
| System user guide | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Architecture diagram and description | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/architecture.png](docs/architecture.png), [docs/architecture.drawio](docs/architecture.drawio) (editable) |
| Design decisions | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Red-team test suite | [redteam/plan.md](redteam/plan.md), with evidence in [redteam/results/](redteam/results/) |
| Threat model (MAESTRO + OWASP LLM and Agentic Top 10) | [threat_model/MAESTRO_mapping.md](threat_model/MAESTRO_mapping.md) |
| How to run everything | [run_instructions.md](run_instructions.md) |

## Repo layout
```
app/
  main.py             FastAPI app: UI, API, and red-team test endpoints (RT-01 to RT-08)
  agent.py, retriever.py, refund.py   starter demo code and the RT-02 mock refund tool
  titanic/
    orchestrator.py   orchestrator agent: planner, MCP router, response aggregator
    agents.py         the five specialized agents and their MCP servers
    gate.py           authorization / policy gate (R1-R7)
    tools.py          agent tools, mock email and payment services
    store.py          long-term memory (SQLite)
    vectordb.py       vector database (Chroma)
    memory.py         short-term memory
    audit.py          append-only, hash-chained audit log
    llm.py            Claude Haiku 5.5 client (API key from the environment)
    redteam.py        red-team tests RT-03 to RT-08
    api.py, ui/       browser UI and its API
data/seed/            synthetic customers, orders, case files, policies
docs/                 user guide, architecture, decisions, screenshots
redteam/              test plan, canned test data, results, negative controls
threat_model/         MAESTRO threat model
```

The original starter instructions still apply: `run_demo.py` walks through the starter endpoints, and `run_instructions.md` covers everything.
