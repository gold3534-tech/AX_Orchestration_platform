# AX Architecture Review & Optimization Guide

Date: 2026-05-06

This guide is an internal self-review standard for AX. Use it before adding major features, changing runtime behavior, introducing new nodes/tools/actions, or reviewing architecture drift.

AX is still in a prototype phase, but the platform must not collapse under its own speed. This guide exists to catch design errors early, protect modularity, reduce unnecessary LLM dependency, and keep AX extensible enough to grow into a Python-first orchestration platform.

## Purpose

Use this guide to answer four questions:

1. Does this design fit the long-term AX philosophy?
2. Does it preserve clean module boundaries?
3. Does it keep execution deterministic, observable, and testable?
4. Does it avoid making LLMs do work that static Python nodes should own?

This document is not a one-time report. It is a recurring checklist for self-review.

Use it for:

- Feature design review
- PR review
- Runtime architecture review
- Tool/action/node design review
- Cleanup and modularization planning
- Prototype debt triage

## AX Architecture Philosophy

AX is not a CrewAI-based platform. AX is a Python-first orchestration platform that can use CrewAI.

CrewAI and any future orchestration framework should be treated as a selectable runtime adapter. They may help implement AX philosophy, but they are not the philosophy itself.

The core AX contract is:

- Schema-first task design
- Deterministic node execution
- Published runtime snapshots
- Explicit data routing
- Runtime adapter independence
- Controlled LLM usage
- Strong module boundaries

### Python-First Orchestration

AX should evolve from "AI orchestration" into Python-first orchestration.

LLMs should be used where they are genuinely valuable:

- Reasoning
- Planning
- Classification
- Natural language generation
- Ambiguous input interpretation
- Creative transformation
- Human-like judgment

Static Python nodes should own deterministic work:

- Google Sheets updates
- URL collection and normalization
- Data scraping
- Image generation API calls
- File upload and download
- Format conversion
- External API execution
- Repeated data processing
- Side-effect operations
- Any operation where call count, cost, output count, or idempotency matters

Core rule:

> Do not assign work to an LLM when a deterministic Python node can do it more safely.

### Crew As A Wrapper

AX may still use Crew-like abstractions, but the meaning of a Crew should expand.

Instead of treating Crew as only a collection of Agents and Tasks, AX should treat a Crew as an orchestration wrapper:

```text
Crew
= Agent
+ Task
+ AX Tool Node
+ Execution Node
+ Data Routing
```

This keeps Agent behavior useful without letting Agent autonomy control every side effect.

### Schema-First Tasks

Tasks should define expected outputs before runtime. A Task should not only say what the Agent should do; it should describe the structured result AX expects.

Example:

```text
Task 1 output
- product_url
- product_title
- image_prompt
```

Those outputs should be routed explicitly:

```text
product_url -> Scraping Node
product_title -> Copywriting Task
image_prompt -> Image Generation Node
```

This makes AX closer to a factory automation system than a prompt chain. Data moves through typed outputs and explicit routing, not vague natural-language handoff.

### Runtime Adapter Independence

AX should prefer working with existing frameworks when they fit, but AX must be able to leave a framework when it conflicts with the platform philosophy.

Review question:

> Are we designing AX around its own stable contracts, or are we leaking one framework's assumptions into the product model?

The product should not depend on any single framework's internal representation for long-term survival.

## AX Architecture Principles

### Versioned Assets

Agents, Tasks, Crews, Flows, Tools, Knowledge, and related platform objects should behave as reusable assets, not one-off runtime blobs.

Review for:

- Clear asset identity
- Immutable version behavior where appropriate
- Restore/delete behavior
- Compatibility with existing asset lifecycle rules
- Avoidance of hidden runtime-only state

### Draft Graph vs Published Runtime Snapshot

Editing state and execution state must stay separate.

- Draft graph: editable UI state
- Published runtime snapshot: execution contract

Execution should use published runtime snapshots, not UI draft state, legacy workflow tables, or ad hoc frontend assumptions.

Blocker:

- Runtime execution depends on draft graph state.
- Runtime behavior changes without publishing a new snapshot.
- Published snapshots are missing fields required to reproduce execution.

### API Contract Discipline

Backend and frontend must communicate through explicit contracts.

When API shape changes:

1. Update backend schema.
2. Update route/service behavior.
3. Regenerate `docs/openapi.json`.
4. Regenerate frontend API types.
5. Update frontend API wrappers and hooks.
6. Add or update tests.

Blocker:

- Frontend manually assumes backend response shape outside generated/API boundary.
- Backend changes contract without OpenAPI/type update.
- Error responses become inconsistent or unsafe for users.

### Boundary Ownership

Each layer should own a narrow responsibility:

- Routes own HTTP concerns.
- Services own persistence orchestration and domain rules.
- Runtime modules own execution assembly.
- Loaders own graph-to-snapshot conversion and validation.
- Tools/actions own provider-specific execution.
- Frontend API modules own HTTP calls.
- Frontend hooks own React Query and domain mapping.
- Pages own workflow state and composition.
- Shared components own reusable UI primitives.

Blocker:

- A UI component learns backend persistence details.
- A service owns runtime execution policy and provider SDK logic at the same time.
- A loader becomes a general-purpose persistence service.
- One file becomes the only place new platform behavior can be added.

## Review Model

Each domain receives a score from `0` to `5`.

| Score | Meaning |
| ---: | --- |
| 5 | Strong fit. Modular, testable, extensible, and aligned with AX principles. |
| 4 | Safe fit. Minor improvements exist, but no structural concern. |
| 3 | Acceptable with caution. Works now, but creates visible follow-up cleanup. |
| 2 | Risky. Design debt will likely affect future features. |
| 1 | Fragile. High maintenance cost or unclear change impact. |
| 0 | Broken. Violates AX architecture principles or needs redesign. |

Final verdict:

| Verdict | Korean | Criteria |
| --- | --- | --- |
| Pass | 통과 | Average score is at least `4.0`, no blocker, and no domain below `3`. |
| Caution | 주의 | Average score is at least `3.0`, but at least one domain needs explicit follow-up. |
| Blocker | 차단 | Any blocker condition is present, regardless of average score. |

Immediate blocker conditions:

- Execution bypasses published runtime snapshots.
- API contract, OpenAPI, or generated frontend type flow is broken.
- User/workspace ownership or credential boundaries are violated.
- A new design worsens god-files, orphan files, duplicate modules, or hidden coupling.
- LLM/tool execution is non-deterministic where output count, cost, or side effects must be controlled.
- Core runtime, auth, persistence, or external action behavior changes without tests.
- Static work is delegated to an Agent only because the tool already exists.
- Task output is passed forward as unstructured prose when downstream routing needs structure.

## Review Domains

### 1. 제품 적합성 및 범위

Check whether the feature belongs in AX and whether the scope is appropriately sized.

Questions:

- Does this fit Agent, Task, Crew, Flow, Tool, Knowledge, Credential, or Runtime Snapshot concepts?
- Is this a platform primitive or a one-off special case?
- Is the feature small enough to design, test, and review?
- Does it avoid solving future problems too early?

Low-score signals:

- Feature creates a separate lifecycle outside the existing asset model without a strong reason.
- Scope mixes unrelated concerns such as UI redesign, provider integration, runtime refactor, and auth changes.
- The feature is useful but not reusable as a platform capability.

### 2. 모듈화 및 코드베이스 위생

Check whether the design protects AX from structural collapse.

Questions:

- Are we creating a reusable module or adding more conditions to a god-file?
- Is there already a component, hook, service, loader, tool, or helper that should be reused?
- Are new files connected to actual runtime/import paths?
- Can the module be understood without reading unrelated internals?
- Can the implementation be replaced without breaking consumers?

Low-score signals:

- Orphan files are created or left behind.
- A large file receives another unrelated responsibility.
- Existing reusable modules are duplicated under a new name.
- Simple logic is hidden behind premature abstraction.
- Provider-specific logic leaks into shared orchestration paths.

Blocker:

- The only way to add the next similar feature is to keep editing the same growing file.
- The design knowingly creates disconnected files, duplicate code paths, or unclear ownership.

### 3. 도메인 경계

Check whether each layer keeps its responsibility.

Questions:

- Are route, service, runtime, schema, model, and frontend boundaries clear?
- Does the backend expose stable contracts instead of frontend-specific internals?
- Does the frontend use `src/api/*` and hooks instead of scattering HTTP details?
- Does runtime code avoid direct UI or draft assumptions?

Low-score signals:

- Frontend components duplicate backend validation logic.
- Service modules directly know too much about provider SDK details.
- Runtime modules perform database mutation that belongs in services.
- Page components own mapping logic that belongs in adapters or hooks.

### 4. API 계약

Check whether API behavior is explicit, typed, and synchronized across backend and frontend.

Questions:

- Are request and response schemas updated?
- Is `docs/openapi.json` regenerated when needed?
- Are generated frontend types updated?
- Are API wrappers and error parsing kept inside frontend API modules?
- Are user-safe errors preserved?

Low-score signals:

- Frontend uses `any` or manual assumptions for new backend fields.
- Error shapes differ from existing API behavior.
- Backend schema accepts ambiguous payloads without validation.

### 5. 데이터 모델 및 영속성

Check whether data storage supports versioning, ownership, deletion, and future migration.

Questions:

- Does the data belong in existing asset/version/snapshot tables or a new table?
- Are migrations explicit and reversible enough for the prototype phase?
- Are indexes aligned with expected query patterns?
- Are delete, restore, and cascade behaviors predictable?
- Is workspace/user ownership enforced in queries?

Low-score signals:

- JSON blobs hide fields that must be queried or validated.
- New tables lack ownership fields.
- Deletion leaves dangling bindings or storage objects.
- Runtime depends on mutable rows instead of immutable snapshots.

### 6. 런타임 스냅샷 및 실행

Check whether execution is reproducible and independent from editing state.

Questions:

- Does publish produce a complete runtime snapshot?
- Can execution run from the snapshot alone?
- Are tools, credentials, knowledge, inputs, and bindings captured or resolvable through stable references?
- Are failures recorded in run events or state snapshots?

Low-score signals:

- Runtime needs to reload draft graph details.
- Execution behavior changes because a mutable asset was edited after publish.
- Snapshot fields are implicit or inferred differently in different code paths.

### 7. AI Agent 및 Flow 품질

Check whether AI is used only where it creates real value.

Questions:

- Is this work better handled by an Agent, an LLM node, a static AX Tool Node, or an Execution Action?
- Does the Task have an output schema?
- Can downstream nodes consume structured output instead of prose?
- Is tool invocation count controlled?
- Are external side effects deterministic and auditable?

Low-score signals:

- Prompt instructions are used for deterministic data routing.
- Agent tool calls are used for fixed side-effect operations.
- Image generation, scraping, uploading, or spreadsheet updates happen inside uncontrolled Agent loops.
- Agent output is free-form text when the next step needs typed fields.

Blocker:

- LLM autonomy controls external side effects that AX must own.
- The design cannot bound LLM calls, tool calls, output count, or provider cost.

### 8. 보안 및 자격 증명 경계

Check whether secrets, users, workspaces, and external accounts stay isolated.

Questions:

- Is Supabase auth or equivalent user identity enforced?
- Are workspace/user ownership checks present?
- Are OAuth tokens and API keys kept out of frontend payloads and prompts?
- Are provider errors redacted?
- Are public artifact metadata and URLs safe?

Low-score signals:

- Credential data is mixed into Agent prompts.
- Provider tokens appear in logs or run events.
- Artifact metadata exposes sensitive provider URLs.
- Queries trust frontend-supplied ownership fields.

### 9. 신뢰성, 관측성 및 오류 처리

Check whether failures are expected, visible, and recoverable.

Questions:

- Are retry, timeout, idempotency, and duplicate side effects considered?
- Are run events detailed enough for debugging?
- Do failures become user-safe messages?
- Can interrupted runs be diagnosed?
- Are partial failures represented clearly?

Low-score signals:

- External action can run twice without idempotency protection.
- User only sees generic failure.
- Logs help developers but run events do not help users.
- Failure state is hidden in free-form text.

### 10. 성능 및 비용 최적화

Check whether the design controls compute, database, storage, and LLM cost.

Questions:

- Are database queries indexed and scoped?
- Does frontend caching avoid unnecessary refetch?
- Are LLM calls minimized and justified?
- Are tool calls bounded?
- Are artifacts and embeddings stored with lifecycle policy?

Low-score signals:

- LLM is used for simple parsing, routing, or deterministic API calls.
- Repeated tool calls happen inside Agent reasoning loops.
- Large data is repeatedly fetched without pagination or caching.
- Embeddings or generated artifacts have no cleanup policy.

### 11. 테스트 및 검증

Check whether the risk level is matched by tests.

Questions:

- Are backend contract tests updated?
- Are runtime loader/factory/executor tests updated?
- Are frontend API and smoke tests updated?
- Are failure paths tested?
- Are migrations validated?

Low-score signals:

- Only happy paths are tested.
- Runtime changes are covered by UI tests only.
- Auth, credential, persistence, or external action changes lack failure-path tests.
- Generated API types are not verified after schema changes.

## Modularization Playbook

### Orphan File Review

A file is suspicious when:

- It is not imported.
- It is not referenced by routes, tests, runtime loaders, or build config.
- It duplicates an older implementation.
- It lives in a `Not_use`, `old`, or temporary path without a clear reason.

Review action:

- Delete it if clearly unused and in scope.
- Move it to documented archive only if historical context matters.
- Record it in `docs/cleanup-candidates.md` if cleanup is outside current scope.

### God-File Review

A file is becoming a god-file when:

- It owns validation, persistence, execution, serialization, and provider logic together.
- Every new capability requires editing it.
- Tests for the file become very large because the file has too many reasons to change.
- Internal helper functions cannot be named without vague words like `handle`, `process`, or `manage`.

Split candidates:

- `validator`: validates contracts and invariants.
- `adapter`: converts between shapes.
- `loader`: builds runtime snapshot from graph/data.
- `executor`: executes one clear runtime unit.
- `registry`: maps keys to implementations.
- `provider`: owns external SDK behavior.
- `serializer`: normalizes output.

### Duplicate Module Review

Before creating a file, search for existing:

- API wrappers
- hooks
- adapters
- runtime helpers
- provider clients
- shared UI components
- test factories
- schema models

Review question:

> Is this new file a new responsibility, or a second implementation of an existing responsibility?

### Complexity Review

Prefer direct code until complexity is real. Add abstraction when it removes meaningful duplication or creates a stable extension point.

Low-score patterns:

- A generic engine for one known use case
- Deep config nesting before the product needs it
- Multiple state machines for one workflow
- Prompt logic replacing typed routing
- Boolean flags accumulating instead of separate node/action types

## Optimization Playbook

### Convert Agent Tool Work To Static Nodes

Use a static AX Tool Node or Execution Node when:

- The operation has external side effects.
- Output count must be fixed.
- Provider cost must be bounded.
- The result should be auditable.
- The operation is deterministic Python work.

Examples:

- Google Sheets update
- Google Drive upload
- Instagram publish
- Image generation API call
- Product scraping
- URL extraction and normalization

### Introduce Task Output Schemas

Use structured outputs when downstream steps need specific fields.

Good:

```json
{
  "product_url": "https://example.com/item",
  "product_title": "Sample title",
  "image_prompt": "A clean product image prompt"
}
```

Risky:

```text
I found the product and here are some ideas...
```

### Stabilize Runtime Snapshots

When execution behavior is unclear, ask:

- Is this field captured at publish time?
- Is this field resolved at run time through a stable reference?
- Could editing a draft change an already-published run?
- Could two runtime paths interpret the same snapshot differently?

### Reduce Cost At The Architecture Level

Do not optimize only prompts. Optimize the graph.

Cost reduction patterns:

- Replace LLM routing with typed routing.
- Replace Agent tool calls with static nodes.
- Cache provider responses where safe.
- Add call limits to tool nodes.
- Move repeated parsing to Python.
- Use smaller LLMs for schema extraction and larger LLMs only for high-value generation.

### Record Deferred Cleanup

If cleanup is real but out of scope, record it.

Use `docs/cleanup-candidates.md` for:

- Orphan files
- God-files
- Duplicate modules
- Known boundary leaks
- Large test files that need fixture extraction
- Provider-specific logic inside shared runtime modules

Do not silently accept architecture debt. Either fix it or name it.

## Review Templates

### 아키텍처 리뷰 결과

```md
## 아키텍처 리뷰 결과

최종 판정: 주의
평균 점수: 3.6 / 5

| 리뷰 영역 | 점수 | 메모 |
| --- | ---: | --- |
| 제품 적합성 및 범위 | 4 | AX capability model에 맞음 |
| 모듈화 및 코드베이스 위생 | 2 | 기존 service에 책임이 더 누적됨 |
| 도메인 경계 | 3 | frontend hook 경계는 유지되지만 runtime adapter 분리가 필요함 |
| API 계약 | 4 | OpenAPI/typegen 흐름 유지 |
| 데이터 모델 및 영속성 | 3 | 삭제 정책 추가 명시 필요 |
| 런타임 스냅샷 및 실행 | 4 | published snapshot 기준 유지 |
| AI Agent 및 Flow 품질 | 2 | 정적 노드로 분리 가능한 작업이 Agent tool에 남아 있음 |
| 보안 및 자격 증명 경계 | 5 | secret 노출 없음 |
| 신뢰성, 관측성 및 오류 처리 | 3 | 실패 이벤트는 있으나 retry/idempotency 보강 필요 |
| 성능 및 비용 최적화 | 3 | LLM 호출 수 제한 필요 |
| 테스트 및 검증 | 4 | backend/runtime 테스트 포함 |

## 필수 개선 액션

- provider별 실행 로직을 shared executor에서 분리한다.
- Agent tool로 처리 중인 정적 작업을 AX Tool Node 후보로 기록한다.
- credential 만료 실패 경로 테스트를 추가한다.

## 후속 정리 후보

- god-file 분리가 이번 범위에 어렵다면 `docs/cleanup-candidates.md`에 기록한다.
- 중복 adapter/helper 후보를 검색하고 재사용 가능성을 확인한다.
```

### PR 리뷰 체크리스트

```md
## AX PR Architecture Checklist

- [ ] 이 변경은 AX 철학과 맞는다.
- [ ] LLM이 필요 없는 작업을 LLM에게 맡기지 않는다.
- [ ] Task output이 downstream routing에 필요한 만큼 구조화되어 있다.
- [ ] 실행은 published runtime snapshot 기준이다.
- [ ] API contract, OpenAPI, frontend generated types가 일치한다.
- [ ] user/workspace ownership과 credential boundary가 유지된다.
- [ ] 새 파일은 기존 재사용 후보를 확인한 뒤 추가되었다.
- [ ] god-file에 새 책임을 누적하지 않았다.
- [ ] 외부 side effect는 deterministic node/action으로 통제된다.
- [ ] failure path, auth path, runtime path 테스트가 있다.
```

### 리스크 로그

```md
| 리스크 | 영향 | 판정 | 대응 |
| --- | --- | --- | --- |
| Agent가 image generation tool을 여러 번 호출할 수 있음 | 비용 증가, output count 불안정 | 차단 | AX Tool Node로 분리하고 max_calls_per_node 적용 |
| 새 provider 로직이 shared executor에 추가됨 | god-file 악화 | 주의 | provider adapter로 분리 |
| Task output schema 없음 | downstream 분배 불안정 | 주의 | Pydantic/JSON schema 추가 |
```

## Examples

### Google Sheets Update

Bad fit:

- Agent receives a Google Sheets tool.
- Prompt says "update the sheet exactly once."
- Agent may call the tool zero, one, or many times.
- Output URL is recovered from natural-language final answer.

Better fit:

- Task generates structured rows.
- Static Google Sheets Node receives rows.
- Node performs deterministic update.
- Node returns structured `spreadsheet_url`, `updated_range`, and `row_count`.

Verdict:

- Agent tool path: usually `주의` or `차단`
- Static node path: usually `통과`

### Image Generation

Bad fit:

- Agent owns image generation tool.
- Prompt says "generate one image."
- Runtime cannot guarantee one image.

Better fit:

- Task produces `image_prompt`.
- AX Image Generation Node receives prompt.
- Node has `max_calls_per_node = 1`.
- Node returns official artifact metadata.

### Knowledge Base

Good fit:

- User uploads knowledge as a platform asset.
- Chunks and embeddings belong to AX storage.
- Agent version binds ready knowledge items.
- Published Crew snapshot captures knowledge bindings.
- Runtime retrieval is a controlled capability.

Review focus:

- Ownership checks
- Deletion cascade
- Embedding cost
- Runtime snapshot completeness
- Future adapter independence

### Execution Action

Use Execution Action when AX must own:

- Approval
- Idempotency
- External side effects
- Durable artifact handling
- Provider-specific lifecycle
- Auditability

Common examples:

- Publish content
- Upload files
- Send messages
- Update external systems

## Self-Review Routine

Before accepting an architecture change:

1. Score all 11 review domains.
2. Check immediate blocker conditions.
3. Identify static-node candidates currently assigned to Agents.
4. Search for reusable modules before approving new files.
5. Check whether any god-file gets worse.
6. Confirm published runtime snapshot behavior.
7. Confirm tests match the risk level.
8. Record deferred cleanup instead of leaving it implicit.

The goal is not perfection in one step. The goal is to keep AX from becoming impossible to extend.
