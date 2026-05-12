# AX Platform - Coding Agent Map

이 문서는 사람용 랜딩 소개가 아니라, 코딩 에이전트와 엔지니어가 AX 프로젝트를 빠르게 파악하기 위한 작업 지도입니다. 새 작업을 시작하면 현재 사용자 요청과 실제 코드를 우선하고, 이 문서는 구조 파악용 배경 자료로 쓰세요.

## Project Snapshot

AX는 웹 기반 AI 오케스트레이션 플랫폼입니다. 사용자는 UI에서 `Agent`, `Task`, `Crew`, `Flow`, `Tool`, `Knowledge`, `Credential`, `Execution Action`을 구성하고, React Flow 기반 빌더 캔버스에서 연결한 뒤, 게시된 runtime snapshot을 통해 CrewAI 워크플로우를 실행합니다.

핵심 원칙:

- `agent`, `task`, `crew`, `flow`는 모두 DB에 저장되는 versioned asset입니다.
- Crew/Flow Builder의 편집 상태는 draft graph로 저장되고, 실행은 published runtime snapshot만 읽습니다.
- 실행 경로는 legacy workflow table이 아니라 `flow_versions.runtime_snapshot_json`과 `asset_runtime_snapshots.runtime_snapshot_json`을 기준으로 합니다.
- Runtime은 CrewAI 객체 조립, HITL 재시도/피드백, tool execution, artifact 저장, event streaming, execution action 승인/실행을 담당합니다.
- Knowledge는 PDF 업로드, 텍스트 추출, OpenAI embedding, pgvector 검색, Agent별 Knowledge Search Tool 연결로 이어집니다.
- 프런트엔드는 `docs/openapi.json`에서 생성한 타입과 `frontend/src/api/*` 경계를 통해 백엔드와 통신합니다.

## Repository Layout

```text
.
├── backend/                    FastAPI, SQLAlchemy, CrewAI runtime
│   ├── api/
│   │   ├── main.py             FastAPI app, router wiring, CORS, DB error handlers
│   │   ├── dependencies.py     Supabase/JWT auth boundary
│   │   ├── core/               DB session, schema/system drift helpers
│   │   ├── db/models/          SQLAlchemy tables
│   │   ├── integrations/       Google, Meta, provider API clients
│   │   ├── routes/             HTTP route layer
│   │   ├── schemas/            Pydantic API contracts
│   │   ├── services/           DB orchestration and domain logic
│   │   ├── runtime/            graph loaders, CrewAI factory, flow execution, events
│   │   └── tools/              AX-owned CrewAI tools
│   ├── sql/                    ordered schema migration notes and DDL
│   ├── supabase/               Supabase-facing assets/config if needed
│   └── tests/                  backend contract/runtime tests
├── frontend/                   React 19, Vite, TanStack Query, React Flow, Pixi
│   ├── src/api/                backend API boundary
│   ├── src/app/                route tree and app providers
│   ├── src/components/         shared layout, platform, canvas, form primitives
│   ├── src/features/           page-level domains
│   ├── src/hooks/              auth and query key helpers
│   ├── src/lib/                shared client/runtime setup
│   ├── src/styles/             globals, tokens, React Flow overrides
│   ├── src/types/              generated OpenAPI types
│   └── tests/smoke/            frontend smoke/contract tests
├── docs/
│   ├── openapi.json            backend contract snapshot for frontend generation
│   ├── ax-tool-addition-guide-map.md
│   ├── runtime-animation-event-types.md
│   ├── cleanup-candidates.md
│   └── superpowers/            design, plans, and implementation history
└── data/                       example and legacy/reference data
    └── mocking_data/           example-only CrewAI shapes; never runtime input
```

## Read This First

Recommended order for new work:

1. This file.
2. Current user request and recent conversation.
3. `docs/openapi.json` when API shape matters.
4. Relevant backend route, schema, service, model, runtime files.
5. Relevant frontend API wrapper, feature hook, page/component/test files.
6. `docs/ax-tool-addition-guide-map.md` for tools, capabilities, execution actions, artifacts, and provider credentials.
7. `docs/runtime-animation-event-types.md` for run event streaming and animation contracts.
8. `data/mocking_data` only as reference shapes.

`data/mocking_data` is not runtime input. Do not hard-code its filenames, paths, agent names, tool names, or YAML structure into production logic.

## Core Data Flow

### Asset CRUD

```text
Build UI
-> frontend/src/api/assets.ts
-> /api/assets
-> backend/api/routes/assets.py
-> backend/api/services/assets.py
-> assets / asset_versions
-> asset_runtime_snapshots / flow_versions
```

`POST /api/assets` creates the first immutable version. `PATCH /api/assets/{asset_id}` appends a new immutable version. Version restore/delete/status logic lives in `backend/api/services/assets.py`.

### Crew Builder

```text
Crew UI
-> frontend/src/api/crewGraphs.ts
-> /api/crew-graphs/{crew_asset_id}/draft
-> crew_version_drafts.graph_json
-> backend/api/runtime/loaders/crew_graph_loader.py
-> asset_runtime_snapshots.runtime_snapshot_json on publish
```

Crew draft is editable canvas state. Publish validates agent/task/tool/knowledge links and creates the runtime crew snapshot that `CrewAIFactory` later uses.

### Flow Builder

```text
Flow UI
-> frontend/src/api/flowGraphs.ts
-> /api/flow-graphs/{flow_asset_id}/draft
-> flow_version_drafts.graph_json
-> backend/api/runtime/loaders/flow_graph_loader.py
-> flow_versions.runtime_snapshot_json on publish
```

Flow snapshots reference published Crew snapshots. Flow Builder uses `/api/flow-graphs/published-crews` for the current user's published Crew options.

### Flow Run

```text
Run/Home UI
-> frontend/src/api/runs.ts
-> /api/flow-runs
-> backend/api/services/runs.py
-> backend/api/runtime/flow_snapshot_executor.py
-> backend/api/runtime/linear_flow_runtime.py
-> backend/api/runtime/crewai_factory.py
-> flow_runs / flow_run_events / flow_run_state_snapshots / human_feedback_requests / run_artifacts
```

Runs execute published Flow snapshots. Crew nodes become CrewAI executions, HITL nodes create and resolve `human_feedback_requests`, execution action nodes use AX-managed action executors, and event writers persist redacted `flow_run_events`.

### Runtime Event Streaming

```text
frontend/src/features/runs/useFlowRunStream.ts
-> WebSocket /api/flow-runs/{run_id}/stream
-> backend/api/routes/runs.py
-> flow_run_events
-> frontend/src/features/streaming/*
-> frontend/src/features/home/HomePixiStage.tsx
```

Stream consumers must tolerate unknown event types. Known event families include run, crew, task, agent, tool execution, collaboration, HITL, rejection, artifact/image progress, and execution action events.

### Knowledge / RAG

```text
Knowledge UI
-> frontend/src/api/knowledge.ts
-> /api/knowledge and /api/knowledge/upload
-> backend/api/services/knowledge.py
-> backend/api/services/knowledge_pdf.py
-> backend/api/services/knowledge_storage.py
-> backend/api/services/knowledge_embeddings.py
-> knowledge_items / knowledge_chunks / version_knowledge_items
-> backend/api/runtime/knowledge_search_tool.py
```

Knowledge PDF upload stores source metadata, extracts readable PDF text, chunks it, embeds it with OpenAI `text-embedding-3-small`, persists pgvector-compatible chunk vectors, and attaches selected items to asset versions. At runtime, attached items are exposed through `AXKnowledgeSearchTool`.

### Capabilities, Tools, And Execution Actions

```text
Capability UI
-> frontend/src/api/capabilities.ts / tooling.ts / connectedAccounts.ts
-> /api/capabilities /api/execution-actions /api/tool-catalog /api/connected-accounts
-> backend/api/services/capabilities.py
-> backend/api/services/tooling.py
-> backend/api/runtime/tool_loader.py
-> backend/api/runtime/execution_actions.py
```

AX uses two capability classes:

- `agent_tool`: Agent/Task-callable tools used during CrewAI reasoning.
- `Execution_Action`: explicit Flow nodes for AX-managed lifecycle, approval, idempotency, artifacts, external publishing, or durable provider side effects.

Use `docs/ax-tool-addition-guide-map.md` before adding a provider integration or tool.

## Backend Map

| Area | Routes | Service/runtime | Data |
| --- | --- | --- | --- |
| Health/Auth | `routes/auth.py`, `/api/auth/*`, `/api/health` | `supabase_client.py`, `dependencies.py` | Supabase OAuth/JWT |
| Assets | `routes/assets.py`, `/api/assets` | `services/assets.py` | `assets`, `asset_versions`, `asset_runtime_snapshots` |
| Crew Graphs | `routes/crew_graphs.py`, `/api/crew-graphs/*` | `services/crew_graphs.py`, `runtime/loaders/crew_graph_loader.py` | `crew_version_drafts`, `asset_runtime_snapshots` |
| Flow Graphs | `routes/flow_graphs.py`, `/api/flow-graphs/*` | `services/flow_graphs.py`, `runtime/loaders/flow_graph_loader.py` | `flow_version_drafts`, `flow_versions` |
| Runs | `routes/runs.py`, `/api/flow-runs/*` | `services/runs.py`, `services/run_recovery.py`, `runtime/flow_snapshot_executor.py`, `runtime/linear_flow_runtime.py` | `flow_runs`, events, state snapshots, HITL, artifacts, action runs |
| Runtime settings | `routes/runtime.py`, `/api/credentials`, `/api/versions/{version_id}/bindings` | `services/runtime.py`, `runtime/credential_*` | `credentials`, `credential_secrets`, `execution_bindings` |
| Connected accounts | `routes/connected_accounts.py`, `/api/connected-accounts/*` | `services/connected_accounts.py`, `runtime/oauth_clients.py`, `integrations/*_oauth.py` | OAuth credentials and states |
| Capabilities | `routes/capabilities.py`, `/api/capabilities`, `/api/execution-actions` | `services/capabilities.py`, `runtime/execution_actions.py` | capability projections, action contracts |
| Tooling | `routes/tooling.py`, `/api/tool-catalog`, `/api/versions/{version_id}/tools` | `services/tooling.py`, `runtime/tool_loader.py`, `runtime/tool_metadata.py` | `tool_catalog`, `version_tools`, `skill_catalog`, `version_skills` |
| Knowledge | `routes/knowledge.py`, `/api/knowledge`, `/api/knowledge/upload`, `/api/versions/{version_id}/knowledge` | `services/knowledge*.py`, `runtime/knowledge_search_tool.py` | `knowledge_items`, `knowledge_chunks`, `version_knowledge_items` |
| Input presets | `routes/task_input_presets.py`, `/api/input-presets` | `services/task_input_presets.py` | `input_preset_definitions`, `task_input_preset_bindings` |
| LLM catalog | `routes/llm_catalog.py`, `/api/llm-catalog` | `services/llm_catalog.py`, `runtime/llm_*` | `llm_catalog` |

Important backend boundaries:

- `api/main.py` registers active routers and maps schema/system DB drift to user-safe 503/422 responses.
- `api/core/database.py` owns SQLAlchemy engine/session creation. Tests default to SQLite unless `DATABASE_URL` is configured.
- `api/db/models/__init__.py` imports all models so `Base.metadata.create_all()` sees them.
- `api/services/assets.py` is the central versioned asset implementation.
- `api/runtime/crewai_factory.py` assembles CrewAI objects from runtime snapshots. It must not read `data/mocking_data`.
- `api/runtime/event_writer.py` and `api/runtime/run_telemetry.py` persist redacted runtime events. Never leak secrets into event payloads.
- `api/runtime/execution_actions.py` owns AX-managed external actions such as Google Drive upload and Instagram publish.
- `api/runtime/artifacts.py`, `api/runtime/supabase_artifact_storage.py`, and provider media URL helpers own artifact/public URL policy.

## Frontend Map

Routes live in `frontend/src/app/routes.tsx`.

```text
/                       -> redirects by auth state
/login                  -> LoginPage
/auth/callback          -> AuthCallbackPage
/home                   -> HomePage with Pixi run animation surface
/build/agents           -> AgentsPage
/build/tasks            -> TasksPage
/build/crews            -> CrewsPage
/build/flows            -> FlowsLibraryPage
/build/flows/:flowId    -> FlowsLibraryPage
/build/tools            -> ToolsLibraryPage
/build/credentials      -> CredentialsPage
/build/knowledge        -> KnowledgePage
/build/settings         -> SettingsPage
/run                    -> RunPage
/run/streaming          -> StreamingPage
/run/io                 -> IOPage
```

Frontend ownership rules:

- `src/api/*`: backend HTTP boundary. Keep request paths, auth headers, response unwrapping, stream URLs, and backend error parsing here.
- `src/features/<domain>/hooks.ts`: React Query calls and domain data mapping.
- `src/features/<domain>/*Page.tsx`: page-level UI and workflow state.
- `src/features/crews/*Canvas.tsx`, `src/features/flows/*Canvas.tsx`: React Flow builder surfaces.
- `src/features/home/*`: home/run orchestration and Pixi animation layer.
- `src/features/runs/*`: run launch, streaming, HITL dialogs, image progress, output previews.
- `src/features/streaming/*`: normalized streaming event models and console UI.
- `src/features/knowledge/*`: Knowledge library, upload, version attachment UI.
- `src/features/credentials/*`: API-key credentials and connected account flows.
- `src/components/layout`: shell, navigation, page framing.
- `src/components/platform`: loading, empty, error, header primitives.
- `src/components/canvas`: shared node/card/panel primitives for builders.
- `src/components/shared`: reusable dialogs/buttons/forms that cross feature boundaries.
- `src/styles/reactflow-overrides.css`: React Flow library styling overrides.
- `src/types/api.generated.ts`: generated from `docs/openapi.json`; do not hand-edit.
- `src/hooks/useAuth.ts`: localStorage token state and auth helpers.
- `src/hooks/queryKeys.ts`: cache key ownership. Add keys here before scattering literal keys.

## API Contract Rules

When backend API shape changes:

1. Update Pydantic schema in `backend/api/schemas/*`.
2. Update route and service behavior.
3. Add or update backend tests.
4. Regenerate `docs/openapi.json`.
5. Run frontend API type generation.
6. Update `frontend/src/api/*`, hooks, UI, and smoke tests.

Commands:

```bash
cd backend
.venv/bin/python -c "import json; from api.main import app; open('../docs/openapi.json', 'w').write(json.dumps(app.openapi(), ensure_ascii=False, separators=(',', ':')))"

cd ../frontend
npm run generate:api
```

## Local Development

Backend:

```bash
cd backend
.venv/bin/python -m uvicorn api.main:app --reload
.venv/bin/python -m pytest
```

Frontend:

```bash
cd frontend
npm run dev
npm test
npm run typecheck
npm run build
```

Useful focused tests:

```bash
cd backend
.venv/bin/python -m pytest tests/test_flow_run_skeleton_v2.py tests/test_flow_run_hitl_v2.py
.venv/bin/python -m pytest tests/test_knowledge_upload_v2.py tests/test_knowledge_runtime_v2.py

cd ../frontend
npm test -- --run tests/smoke/flow-canvas.test.tsx tests/smoke/crew-canvas.test.tsx
npm test -- --run tests/smoke/use-flow-run-stream.test.tsx tests/smoke/run-pages.test.tsx
```

## Environment Notes

`backend/.env.example` is the starting point, but some newer integrations also depend on variables used in tests and runtime code.

Common backend variables:

- `DATABASE_URL`: defaults to in-memory SQLite when unset.
- `CORS_ORIGINS`: comma-separated frontend origins, defaults to `http://localhost:3000`.
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` or `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`.
- `OAUTH_REDIRECT_URL`, `OAUTH_COOKIE_SECURE`.
- `CREDENTIAL_ENCRYPTION_KEY`: Fernet key for encrypted credential secrets.
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `SERPER_API_KEY`, `FIRECRAWL_API_KEY`.
- `GOOGLE_WORKSPACE_CLIENT_ID`, `GOOGLE_WORKSPACE_CLIENT_SECRET`, `GOOGLE_WORKSPACE_REDIRECT_URI`.
- `META_INSTAGRAM_APP_ID`, `META_INSTAGRAM_APP_SECRET`, `META_INSTAGRAM_REDIRECT_URI`, `META_GRAPH_API_VERSION`.
- `AX_ARTIFACT_STORAGE_ROOT`, `AX_SUPABASE_ARTIFACT_BUCKET`, `AX_PUBLIC_BASE_URL`.
- `AX_SUPABASE_KNOWLEDGE_BUCKET`, `AX_KNOWLEDGE_ALLOW_DEMO_EMBEDDINGS`.

Production Knowledge target is OpenAI embeddings plus pgvector. `AX_KNOWLEDGE_ALLOW_DEMO_EMBEDDINGS=1` is local/demo fallback only.

## Common Change Recipes

### Add Or Change An Asset Payload Field

Touch these areas:

- `backend/api/schemas/assets.py`
- `backend/api/services/assets.py`
- related typed model in `backend/api/db/models/*_version.py`
- feature form and hooks under `frontend/src/features/<domain>/`
- API/smoke tests in `backend/tests` and `frontend/tests/smoke`

Do not bypass the shared asset contract unless the asset type genuinely needs separate lifecycle behavior.

### Change Crew Builder Behavior

Touch these areas:

- `frontend/src/features/crews/crewGraphTypes.ts`
- `frontend/src/features/crews/crewGraphAdapters.ts`
- `frontend/src/features/crews/CrewBuilderCanvas.tsx`
- `frontend/src/features/crews/hooks.ts`
- `frontend/src/api/crewGraphs.ts`
- `backend/api/runtime/loaders/crew_graph_loader.py`
- `backend/api/services/crew_graphs.py`
- `backend/tests/test_crew_graph_loader_v2.py`
- `backend/tests/test_crew_graph_routes_v2.py`
- `frontend/tests/smoke/crew-canvas.test.tsx`

### Change Flow Builder Behavior

Touch these areas:

- `frontend/src/features/flows/flowGraphTypes.ts`
- `frontend/src/features/flows/flowGraphAdapters.ts`
- `frontend/src/features/flows/FlowBuilderCanvas.tsx`
- `frontend/src/features/flows/hooks.ts`
- `frontend/src/api/flowGraphs.ts`
- `backend/api/runtime/loaders/flow_graph_loader.py`
- `backend/api/services/flow_graphs.py`
- `backend/tests/test_flow_graph_loader_v2.py`
- `backend/tests/test_flow_graph_routes_v2.py`
- `frontend/tests/smoke/flow-canvas.test.tsx`

### Change Runtime Execution

Touch these areas:

- `backend/api/runtime/linear_flow_runtime.py`
- `backend/api/runtime/flow_snapshot_executor.py`
- `backend/api/runtime/crewai_factory.py`
- `backend/api/runtime/event_writer.py`
- `backend/api/runtime/run_events.py`
- `backend/api/services/runs.py`
- `backend/api/routes/runs.py`
- `backend/tests/test_linear_flow_runtime_v2.py`
- `backend/tests/test_flow_run_skeleton_v2.py`
- `backend/tests/test_flow_run_hitl_v2.py`
- `backend/tests/test_flow_run_websocket_v2.py`
- `backend/tests/test_crewai_event_bridge_v2.py`
- `backend/tests/test_crewai_factory_v2.py`

Do not make execution read builder drafts. Runs should use published Flow snapshots.

### Add Or Change Knowledge

Touch these areas:

- `backend/api/routes/knowledge.py`
- `backend/api/schemas/knowledge.py`
- `backend/api/services/knowledge.py`
- `backend/api/services/knowledge_pdf.py`
- `backend/api/services/knowledge_storage.py`
- `backend/api/services/knowledge_embeddings.py`
- `backend/api/runtime/knowledge_search_tool.py`
- `backend/api/runtime/loaders/crew_graph_loader.py` when Knowledge attachment affects snapshots
- `frontend/src/api/knowledge.ts`
- `frontend/src/features/knowledge/*`
- relevant Crew/Agent version UI when attaching Knowledge
- `backend/tests/test_knowledge_v2.py`
- `backend/tests/test_knowledge_upload_v2.py`
- `backend/tests/test_knowledge_runtime_v2.py`
- `frontend/src/api/knowledge.test.ts`
- `frontend/src/features/knowledge/KnowledgePage.test.tsx`

### Add Or Change A Tool / Capability / Execution Action

Start with `docs/ax-tool-addition-guide-map.md`.

Likely files:

- `backend/api/services/default_crewai_tools.py`
- `backend/api/services/capabilities.py`
- `backend/api/runtime/credential_providers.py`
- `backend/api/runtime/credential_resolver.py`
- `backend/api/runtime/tool_metadata.py`
- `backend/api/runtime/tool_loader.py`
- `backend/api/runtime/execution_actions.py`
- `backend/api/tools/*.py`
- `backend/api/integrations/*.py`
- `backend/tests/test_tooling_v2.py`
- `backend/tests/test_capability_catalog_v2.py`
- provider-specific backend tests
- `frontend/src/api/capabilities.ts`
- `frontend/src/api/tooling.ts`
- `frontend/src/features/tools/*`
- `frontend/tests/smoke/tool-config-panel.test.tsx`

### Change Run Streaming / Home Animation

Touch these areas:

- `backend/api/runtime/run_events.py`
- `backend/api/runtime/event_writer.py`
- `backend/api/runtime/run_telemetry.py`
- `backend/api/routes/runs.py`
- `frontend/src/features/runs/useFlowRunStream.ts`
- `frontend/src/features/streaming/streamingEventModel.ts`
- `frontend/src/features/home/HomePixiStage.tsx`
- `frontend/src/features/home/homePixi*.ts`
- `docs/runtime-animation-event-types.md`
- `backend/tests/test_run_events_v2.py`
- `backend/tests/test_flow_run_websocket_v2.py`
- `frontend/tests/smoke/use-flow-run-stream.test.tsx`

## Current SQL Migration Index

Ordered DDL files live in `backend/sql`:

- `002_task_input_presets.sql`
- `003_crew_draft_persistence.sql`
- `004_flow_builder_persistence.sql`
- `005_drop_workflow_graph_tables.sql`
- `006_add_asset_version_metadata_and_payload_json.sql`
- `007_unify_asset_versions_payload_storage.sql`
- `008_user_credential_secrets.sql`
- `009_flow_hitl_review_gate_runtime.sql`
- `010_flow_run_event_stream_index.sql`
- `011_llm_catalog.sql`
- `012_capability_oauth_execution_actions.sql`
- `013_restore_auth_profiles.sql`
- `014_knowledge_upload_real_rag.sql`

Apply them in sequence for Postgres updates. Tests may create SQLite schema from SQLAlchemy models, but production drift still requires migration discipline.

## Working Rules

- Keep API boundary code in `frontend/src/api/*`.
- Keep domain data fetching and mapping in feature `hooks.ts`.
- Keep builder graph serialization/deserialization in adapters and graph type files.
- Keep runtime execution independent from draft graph state.
- Keep generated files generated: `frontend/src/types/api.generated.ts` and `docs/openapi.json` should be regenerated, not hand-maintained.
- Add tests at the boundary being changed: backend service/runtime tests for behavior, frontend smoke tests for UI contracts.
- Never return secrets in event payloads, artifact metadata, provider URLs, tool output previews, or frontend API responses.
