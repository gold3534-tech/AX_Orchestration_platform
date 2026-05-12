# Backend Domain Contracts

This package is the FastAPI backend for AX. It owns the HTTP API, domain services, runtime assembly, and the SQLAlchemy models that back versioned assets and execution state.

## Main Areas

- `api/main.py`: FastAPI app wiring, router registration, CORS, and DB error handling.
- `api/dependencies.py`: Supabase/JWT auth boundary.
- `api/routes/*`: HTTP route layer.
- `api/services/*`: domain orchestration and persistence logic.
- `api/runtime/*`: graph loaders, CrewAI factory, execution, telemetry, and runtime helpers.
- `api/db/models/*`: SQLAlchemy tables.
- `api/schemas/*`: Pydantic API contracts.
- `api/tools/*`: local tool implementations.
- `sql/*`: schema migration notes and DDL.
- `tests/*`: backend contract and runtime tests.

## Current Contracts

- `agent`, `task`, `crew`, and `flow` are versioned assets behind one shared contract.
- `POST /api/assets` creates the asset and version `1`.
- `PATCH /api/assets/{asset_id}` appends a new immutable version.
- Draft graph state lives in `crew_version_drafts.graph_json` and `flow_version_drafts.graph_json`.
- Published runtime snapshots live in `asset_runtime_snapshots.runtime_snapshot_json` and `flow_versions.runtime_snapshot_json`.
- Flow execution uses published Flow snapshots, not legacy workflow graph tables.
- Tool catalog, runtime credentials/bindings, task input presets, and the LLM catalog remain explicit backend areas.

## Important Files

- `api/services/assets.py`
- `api/services/crew_graphs.py`
- `api/services/flow_graphs.py`
- `api/services/runs.py`
- `api/services/runtime.py`
- `api/runtime/loaders/crew_graph_loader.py`
- `api/runtime/loaders/flow_graph_loader.py`
- `api/runtime/crewai_factory.py`
- `api/runtime/flow_snapshot_executor.py`
- `api/runtime/linear_flow_runtime.py`
- `api/runtime/tool_loader.py`
- `api/runtime/run_telemetry.py`

## Postgres and Tests

- `backend/sql` files are ordered schema notes; apply them in sequence when you need a Postgres update.
- Backend tests live under `backend/tests`.
- Use the backend root when running pytest so paths stay short: `tests/...`, not `backend/tests/...`.
- Keep `docs/openapi.json` and frontend generated types in sync when the API contract changes.

## Working Notes

- `api/main.py` includes the active routers and maps schema or system drift to user-safe responses.
- `api/core/database.py` owns SQLAlchemy engine/session creation. Tests default to SQLite unless configured otherwise.
- `api/db/models/__init__.py` imports models so `Base.metadata.create_all()` sees them.
- `api/services/assets.py` is the central versioned asset implementation. Be careful when touching version status, restore, delete conflict checks, or typed payload serialization.
- `api/runtime/crewai_factory.py` assembles CrewAI objects from runtime snapshots. It should not read `data/mocking_data`.
