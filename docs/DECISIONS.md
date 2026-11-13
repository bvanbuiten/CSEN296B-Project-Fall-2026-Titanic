# Design decisions

The decisions behind Titanic, so the final report builds on them instead of starting over. Newest first.

## Team decisions (Nov 10, 2026)
| Decision | Choice | Why |
|---|---|---|
| Account Management agent | Not a separate agent. Balance, purchase history, and add funds belong to Customer Records Management. | The spec lists five agents, and the proposal lost points because its description named an agent its diagram did not show. |
| Weekly cap scope | One $500 total for the agent across all customers, over a rolling 7 days | The rule limits what the agent does on its own. A rolling window stops "$500 on Sunday, $500 on Monday". |
| Do supervisor-approved refunds count toward $500? | No | The cap limits autonomous refunds. A human already decided these. |
| Boundary values | $100.00 and $500.00 exactly are allowed | "Up to" is inclusive. RT-02 and RT-06 test both edges. |
| Email allowlist (R7) | The customer's address on file, plus `supervisor@titanic.test` | It narrows R3 to email. Address changes go to a human. |
| RT-03 pass condition | Includes "no refund above the order amount" | Matches the shared doc. Enforced by the gate (rule ORDER). |
| Test numbering | As in the shared doc: RT-05 is another customer's records, RT-06 is the weekly cap. RT-07 and RT-08 are additions. | The shared doc rules. |

## Build decisions
| Decision | Choice | Why |
|---|---|---|
| Who enforces the rules | A policy gate in code checks every tool call. The model only proposes. | Prompt injection can change what a model says, but not what the gate allows. |
| Refund amount | Always taken from the case, never from the model | Removes a whole class of injection ("refund $400 instead"). |
| Plan validation | The model proposes the plan; code checks it against the allowed workflow | Goal-hijack protection (ASI01) while keeping LLM-based task decomposition. |
| Agent communication | Real MCP (`mcp` 2.x). One MCP server per agent, connected in-process, with an HMAC-signed context. | The proposal promised MCP. Signing covers insecure inter-agent communication (ASI07). |
| Vector database | Chroma, local, with its default small embedding model | A real vector database with no extra keys. Searches are filtered by customer. |
| Long-term memory | SQLite | Simple, file-based, and easy to sandbox per test. |
| Audit log | Append-only JSON lines, each entry hash-chained to the previous one | Tamper-evident evidence (MAESTRO L5); the supervisor can verify it in the portal. |
| Revocation | Stops all agent work, including reads; queued cases move to the supervisor | Fail-closed reading of "never act after permission is taken away". |
| Without an API key | A deterministic offline stand-in calls the same tools through the same gate | Lets the build and the gate-level tests run before the key arrives. Tests that need the model say NOT RUN instead of faking results. |
| Model | Claude Haiku 5.5 (`claude-haiku-5-5`), effort `medium`, structured JSON outputs | Team choice. Cheap for small synthetic prompts. |
| Dependencies | FastAPI 0.115+ and Pydantic 2.12+, matching Bastiaan's `Bas` branch; plus `anthropic`, `mcp`, `chromadb` | Aligns with the Blue team's upgrade, fixes the Python 3.14 crash of the old pins, and is required by the MCP library. |
| Tests | Each test runs in a fresh throwaway sandbox; verdicts come from side effects; each test has a negative control | Matches the spec's assurance framework: behavioral, execution-boundary, and containment evidence. |
| Sign-in | Synthetic customer ID + PIN; supervisor passcode from an environment variable | Enough to make the session (not the request) decide who the customer is. Not production authentication. |

## Open items
- **API key:** Justin is getting it. RT-03 and RT-04 need it for counted runs.
- **Merge order:** PR #1 (RT-02) needs merging into `main` before this work's PR.
