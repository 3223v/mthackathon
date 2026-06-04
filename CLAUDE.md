# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A LangGraph-based activity planning agent system — an intelligent travel/concierge assistant that generates multi-activity itineraries, supports three replanning modes, streaming chat, transactional order booking, and a matrix-based path selection UI. Backend is Python/FastAPI + WebSocket; frontend is Next.js 16 + React 19 + TailwindCSS 4.

## Commands

### Backend (Python 3.10+)

```bash
cd program/backend
pip install -r requirements.txt          # first-time setup
python main.py                           # dev mode (FastAPI on :8000)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (Node.js 18+)

```bash
cd program/frontend
npm install                              # first-time setup
npm run dev                              # dev server (default :3000)
npm run build                            # production build
```

### LLM config

`program/backend/config/llm_config.json` — supports multiple LLM providers with round-robin failover (gitignored, contains API keys):

```json
[{"name": "OpenAI", "model": "gpt-4o", "base_url": "https://api.openai.com/v1",
  "api_key": "your-key", "temperature": 0.7, "max_tokens": 4096}]
```

## Architecture

### LLMManager — dual-pool design

Two separate LLM instance pools initialized at startup:
- **Streaming pool** (`self.llms`, `streaming=True`) — real-time token streaming to frontend
- **Non-streaming pool** (`self.ns_llms`, `streaming=False`) — structured output (json_schema/function_calling)

Key methods:
- `invoke(messages, stream_callback)` — streaming text call
- `invoke_structured(messages, schema)` — three-layer structured output (json_schema → function_calling → None fallback)
- `invoke_with_logging(system_prompt, user_prompt, stream_callback, log_prefix)` — full prompt/response logging

### LangGraph agent flow

8-node state graph. Entry is always `analyze_intent`, then conditional routing:

```
analyze_intent
  ├─ general → general_response → END
  ├─ preferences → extract_preferences → END
  ├─ planning → extract_preferences → query_data → planner → END
  ├─ replan_full → query_data → planner → END
  ├─ replan_replace → replace_activity → END
  └─ replan_partial → partial_replan → END
```

### Planner node — streaming + post-hoc validation + countdown retry

1. **First attempt**: streaming LLM → frontend real-time display → JSON parse check
2. **Parse failure**: sets `planner_parse_failed=True` in state → WebSocket handler sends `plan_validation_failed` event with 3s countdown
3. **Retry**: directly calls `generate_plan()` (not full graph re-run) → uses non-streaming structured output (json_schema → function_calling)
4. **Frontend**: amber banner with ⏳ countdown + "立即重试" button; auto-retries on timeout

### Structured output (json_schema / function_calling)

Pydantic schemas in `agent/schemas.py`: `PlanOutput`, `PartialReplanOutput`, `IntentOutput`, `RankedIndices`.

`_parse_plan_json()` has 4 strategies: markdown code block extraction → direct parse → balanced-bracket array extraction → common error fix (trailing commas, comments, BOM removal). Detailed diagnostic logging at each failure point.

### Skills mechanism

Scenario-specific planning guides as Markdown files under `skills/`. Three skills: Parent-Child, Friends Outing, Personal/Couple travel. Skill loader parses markdown sections via regex, matches user input against trigger keywords, generates query filters, and injects context into planner prompts.

### Transport calculation (`core/travel.py`)

Haversine distance formula, four transport modes (walking/public_transit/taxi/driving) with speed and overhead constants. `recommend_transport_mode()` adjusts based on children/group size.

### Replanner (`agent/nodes/replanner.py`)

- **replace_activity**: constraint-solving — keyword → fuzzy name → type match → LLM fallback target location; scores alternatives by rating/distance
- **partial_replan**: keeps activities before split point, LLM-generates suffix; uses three-layer structured output
- **full_replan**: clears plan, sets intent to `planning`

### Mock data layer (`mockfunction/__init__.py`)

Single data access point — never read JSON files directly. 7 JSON files under `mockdata/`. Exposes nearby queries, availability checks, booking execution, preference persistence, scenario recommendations.

### Order booking

`POST /api/orders/execute` — three-phase transaction: collect → validate all → execute with rollback.
`POST /api/orders/execute/{index}` — single order, no transaction.

### REST API endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ws/chat` | WS | Real-time chat |
| `/api/orders/validate` | POST | Validate order availability |
| `/api/orders/execute` | POST | Batch execute (transactional) |
| `/api/orders/execute/{i}` | POST | Single execute |
| `/api/plan/alternatives` | POST | Top-K DAG alternatives |
| `/api/plan/matrix` | POST | 2D matrix (columns=positions, rows=original+alternatives) |
| `/api/plan/reroute` | POST | Custom path from DAG |
| `/api/plan/reroute-matrix` | POST | Custom path from matrix |
| `/health` | GET | Health check |

### Frontend

Single-page app in `components/ChatInterface.tsx`. Three-panel layout + overlays:
- **Left**: agent thinking log
- **Center**: streaming chat with error/retry banners
- **Right**: plan panel with activity cards, right-edge arrow buttons for alternative cycling, transport mode switching
- **Overlay**: `MatrixView` component — full-screen 2D path selection, gradient headers, column-based node selection, CustomEvent callback to avoid WebSocket drop

### Logging

Dual console/file logging: console at INFO (truncated), file at DEBUG (full). `log_node_io()` helper for consistent node I/O logging. Log files at `logs/agent_YYYYMMDD.log`.

### Configuration files

- `config/llm_config.json` — LLM providers (gitignored)
- `config/prompts.json` — all system/user/replan prompts
- `config/skills.json` — skill index with trigger keywords

### Adding features

- **New skill**: create `skills/NewSkill/NewSkill.md`, add entry to `config/skills.json`, restart backend
- **New data source**: add JSON to `mockdata/`, add function in `mockfunction/__init__.py`, add wrapper in `tools/query_tools.py`
- **New transport mode**: add entry to `TRANSPORT_MODES` in `core/travel.py`
