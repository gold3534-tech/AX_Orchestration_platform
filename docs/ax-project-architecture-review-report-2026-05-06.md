# AX 프로젝트 전체 아키텍처 리뷰 보고서

작성일: 2026-05-06  
기준 문서: `docs/ax-architecture-review-optimization-guide.md`  
대상 범위: `backend`, `frontend`, `docs/openapi.json`, `backend/sql`, `docs/cleanup-candidates.md`, 테스트 스위트

## 결론

최종 판정: 주의

평균 점수: 3.4 / 5

AX의 큰 방향은 가이드와 잘 맞는다. 특히 versioned asset, draft graph와 published runtime snapshot의 분리, 런타임 ownership 검증, OpenAPI 스냅샷 동기화는 프로젝트 중심축으로 자리 잡았다.

다만 현재 상태는 "프로토타입을 빠르게 정리해 온 구조"와 "다음 단계에서 반드시 갚아야 하는 부채"가 같이 존재한다. 핵심 리스크는 세 가지다.

1. Agent tool이 아직 Google Sheets, Instagram publish 같은 외부 부작용을 직접 실행할 수 있다.
2. `flow_snapshot_executor.py`와 graph loader 계열이 런타임 정책, credential resolution, 이벤트, 실행 액션, CrewAI 조립을 한 파일 흐름에 많이 품고 있다.
3. 프론트/백 테스트가 현재 코드와 일부 불일치하며, 특히 runtime execution 관련 백엔드 테스트 10개와 프론트 계약/모달 테스트 6개가 실패한다.

즉, 지금 바로 "차단"으로 보지는 않지만, 새 provider action, runtime node, cost-sensitive tool을 추가하기 전에는 정적 Execution Action 전환과 런타임 파일 분리가 우선되어야 한다.

## 점수표

| 리뷰 영역 | 점수 | 메모 |
| --- | ---: | --- |
| 제품 적합성 및 범위 | 4 | Agent, Task, Crew, Flow, Tool, Knowledge, Credential, Runtime Snapshot 모델이 README와 실제 라우트 구조에 일관되게 나타난다. |
| 모듈화 및 코드베이스 위생 | 2 | `flow_snapshot_executor.py`, loader, page 파일이 대형화되어 있고 `__pycache__`, `data/Not_use`, old docs가 작업 표면에 남아 있다. |
| 도메인 경계 | 3 | route/service/runtime/frontend api 경계는 대체로 있으나 runtime executor가 너무 많은 도메인을 직접 조율한다. |
| API 계약 | 3 | `docs/openapi.json`은 현재 FastAPI 출력과 일치하지만, 일부 frontend API wrapper가 generated type을 우회한다. |
| 데이터 모델 및 영속성 | 4 | versioned asset, runtime snapshot, credential secret, run artifact 모델은 명확하다. cleanup/retention 운영 정책은 보강 필요. |
| 런타임 스냅샷 및 실행 | 4 | 실행은 published flow version과 runtime snapshot을 기준으로 시작한다. 테스트 실패 때문에 안정성 확신은 낮아진다. |
| AI Agent 및 Flow 품질 | 2 | Instagram publish, Google Sheets write, image/tool side effect가 Agent tool 경로에 남아 있어 AX 철학과 충돌한다. |
| 보안 및 자격 증명 경계 | 4 | owner_user_id 조인, credential secret 분리, event redaction이 있다. public artifact content 정책은 더 엄격한 감사가 필요하다. |
| 신뢰성, 관측성 및 오류 처리 | 3 | run event, state snapshot, recovery가 있으나 실행 이벤트 관련 테스트가 실패하고 retry/idempotency 정책이 action별로 균일하지 않다. |
| 성능 및 비용 최적화 | 3 | LLM catalog와 credential provider 구조는 있으나 Agent loop 내부 tool call 비용/횟수 통제가 아직 약하다. |
| 테스트 및 검증 | 2 | 테스트 양은 충분하지만 현재 전체 스위트가 실패한다. contract drift 감지 기능은 있으나 녹색 상태가 아니다. |

## 주요 근거

### 잘 맞는 부분

- `backend/api/runtime/flow_snapshot_executor.py:102`에서 published flow version, `AssetVersion.status == "published"`, `Asset.asset_type == "flow"`, `Asset.owner_user_id`를 함께 확인한다. 실행이 draft graph를 직접 읽는 구조는 아니다.
- `backend/api/runtime/flow_snapshot_executor.py:1181`의 `_owned_run`은 run 조회 시 asset ownership을 조인해 사용자 경계를 확인한다.
- `backend/api/routes/runs.py:110`, `backend/api/routes/runs.py:149`, `backend/api/routes/runs.py:203` 등 run 생성/조회/HITL 응답 라우트는 `get_current_user`를 직접 요구한다.
- `backend/api/runtime/execution_actions.py:147` 이후는 Execution Action run을 idempotency key로 기록하고 `pending_approval` 상태를 만들 수 있다. AX-managed external action 방향과 잘 맞는 기반이다.
- OpenAPI 비교 결과 `docs/openapi.json`과 현재 FastAPI `app.openapi()`는 동일했다. path 수는 둘 다 50개였다.

### 위험한 부분

- `backend/api/tools/google_sheets_tool.py:36`의 `AXGoogleSheetsTool`은 Agent가 `append_rows`, `update_values`를 직접 실행할 수 있게 한다. 가이드 기준으로 Google Sheets update는 static AX Tool Node 또는 Execution Action 후보이다.
- `backend/api/tools/instagram_publish_tool.py:22`의 `AXInstagramPublishTool`도 Agent tool로 외부 publish를 수행한다. 같은 기능의 AX-managed 경로가 `backend/api/runtime/execution_actions.py:125`에 이미 있으므로 중복 실행 경로가 생긴다.
- `backend/api/runtime/flow_snapshot_executor.py:1364`부터 `execution_action`, `crew`, credential env, OAuth runtime context, event bridge, artifact context, CrewAI kickoff가 한 메서드 흐름에 같이 존재한다. 다음 provider나 node type이 추가될수록 이 파일이 변경 중심이 될 가능성이 높다.
- `frontend/src/api/flowGraphs.ts:1`과 `frontend/src/api/crewGraphs.ts:1`은 generated OpenAPI client 대신 직접 `fetch`와 수동 타입을 사용한다. multipart upload처럼 fetch가 필요한 예외는 이해되지만 graph API 전체가 수동 타입이면 계약 흐름이 약해진다.
- `frontend/src/api/knowledge.ts:18` 등은 `as never`로 generated type을 우회한다. 타입 생성은 되어 있지만 실제 안전성이 낮아진다.
- `backend/api/main.py:33`은 앱 시작 시 `Base.metadata.create_all()`을 실행한다. 프로토타입에는 편하지만 운영 마이그레이션 경계와 drift detection을 흐릴 수 있다.
- `docs/cleanup-candidates.md`에 이미 god-file 후보와 orphan 후보가 기록되어 있다. 실제 파일 목록에서도 `backend/api/**/__pycache__`, `backend/tests/__pycache__`, `.pytest_cache`, `data/Not_use`가 남아 있다.

## 필수 개선 액션

1. Agent tool로 남아 있는 외부 부작용을 Execution Action 또는 static AX Tool Node로 전환한다.
   - 우선순위: Instagram publish, Google Sheets write, image generation, scraping.
   - Agent tool은 read-only 또는 reasoning 보조로 제한하고, publish/write/upload는 Flow node가 실행하게 만든다.

2. `FlowSnapshotExecutor`를 실행 단위별 모듈로 나눈다.
   - 후보 분리: `crew_node_executor`, `execution_action_node_executor`, `hitl_runtime`, `runtime_context_resolver`, `run_failure_recorder`.
   - 목표는 새 node type 추가 시 `flow_snapshot_executor.py`를 최소 수정하는 것이다.

3. frontend graph API wrapper를 generated OpenAPI contract에 다시 붙인다.
   - `flowGraphs.ts`, `crewGraphs.ts`의 수동 envelope 타입을 `paths[...]` 기반으로 바꾼다.
   - `as never` 사용은 multipart upload나 OpenAPI 표현 한계가 있는 곳만 남긴다.

4. 테스트 스위트를 녹색으로 만든다.
   - 프론트: `npm test`에서 46개 파일 중 3개 파일, 344개 테스트 중 6개 실패.
   - 백엔드: `uv run pytest -q`에서 1015개 통과, 1개 skip, 10개 실패.
   - 특히 백엔드 실패는 flow run background, CrewAI event bridge, live crew execution, redaction event, knowledge SQL path에 몰려 있다.

5. cleanup 후보를 실제 작업으로 전환한다.
   - `__pycache__`, `.pytest_cache`가 repo 작업 표면에 보이지 않도록 `.gitignore`와 정리를 확인한다.
   - `data/Not_use`는 삭제, archive, 문서화 중 하나로 결정한다.
   - `docs/cleanup-candidates.md`의 god-file 후보를 이 보고서의 액션과 연결한다.

## 도메인별 상세 리뷰

### 1. 제품 적합성 및 범위

AX는 CrewAI 전용 제품이 아니라 Python-first orchestration platform이라는 가이드 방향과 대체로 맞다. README는 versioned asset, draft graph, published runtime snapshot, Execution Action, Knowledge/RAG를 명확히 설명한다. 현재 기능들이 Agent/Task/Crew/Flow/Tool/Knowledge/Credential/Runtime Snapshot 안에 들어오므로 제품 범위 점수는 높다.

주의점은 provider integration이 아직 "Agent tool로 바로 붙이는 방식"과 "AX-managed Execution Action" 두 경로로 공존한다는 점이다. 앞으로는 새 side-effect provider를 Execution Action 우선으로만 설계해야 한다.

### 2. 모듈화 및 코드베이스 위생

가장 약한 영역이다. `flow_snapshot_executor.py`는 1800라인 이상이고, `crew_graph_loader.py`, `flow_graph_loader.py`, `assets.py`, `flow_graphs.py`, `CrewsPage.tsx`, `FlowsLibraryPage.tsx`도 이미 cleanup 후보로 기록되어 있다. 이 목록은 실제 line count와도 일치한다.

이 상태에서 새 node type, 새 provider, 새 approval policy가 들어오면 같은 파일이 계속 커질 가능성이 크다. 가이드의 god-file warning에 해당한다.

### 3. 도메인 경계

라우트는 HTTP concern을, 서비스는 persistence orchestration을, runtime은 execution을 맡는 기본 경계가 있다. 그러나 runtime executor 내부에서 credential resolution, provider context, CrewAI factory, execution action, HITL, event persistence를 모두 직접 연결한다.

프론트는 대체로 `src/api/*`, feature hooks, page 구조를 지키지만 graph API는 수동 fetch와 수동 타입이 많아 API boundary 품질이 균일하지 않다.

### 4. API 계약

OpenAPI 파일 자체는 현재 앱과 일치한다. 이 점은 좋다.

하지만 계약 discipline은 "파일이 일치한다"만으로 충분하지 않다. `flowGraphs.ts`, `crewGraphs.ts`, `knowledge.ts`, `capabilities.ts`, `connectedAccounts.ts` 일부에서 수동 타입, `Record<string, unknown>`, `as never`가 반복된다. 이 패턴은 backend contract가 바뀌어도 frontend compile 단계에서 놓칠 여지를 만든다.

### 5. 데이터 모델 및 영속성

`assets`, `asset_versions`, `asset_runtime_snapshots`, `credentials`, `credential_secrets`, `flow_runs`, `flow_run_events`, `run_artifacts`, `execution_action_runs` 모델은 AX 원칙과 잘 맞는다. 특히 credential secret 분리와 action idempotency unique key는 좋은 방향이다.

보강할 점은 artifact retention과 public content URL 정책이다. `backend/api/routes/runs.py:332`의 public artifact endpoint는 image metadata가 특정 preview/download path를 가질 때 열리는데, 이 정책은 문서화와 테스트를 더 늘리는 편이 좋다.

### 6. 런타임 스냅샷 및 실행

published snapshot 기준 실행은 구현되어 있다. `load_published_snapshot`이 published flow version과 owner를 확인하고, run state에는 published snapshot entities가 들어간다.

단, 전체 backend 테스트에서 flow run execution 관련 테스트가 다수 실패한다. 실패 원인은 일부 테스트 더블과 factory signature drift일 가능성이 있지만, 결과적으로 현재 테스트는 런타임 안정성을 증명하지 못한다.

### 7. AI Agent 및 Flow 품질

가이드 기준으로 가장 큰 구조 리스크다. Google Sheets write, Instagram publish, image generation, scraping은 output count, provider cost, idempotency, external side effect가 중요한 작업이다. 이런 작업이 Agent tool loop 안에서 실행되면 AX가 통제해야 할 비용과 부작용을 LLM autonomy에 맡기게 된다.

이미 Execution Action infrastructure가 있으므로 방향은 명확하다. Agent에게는 structured output을 만들게 하고, downstream Flow node가 typed field를 받아 실행하게 해야 한다.

### 8. 보안 및 자격 증명 경계

ownership check와 credential boundary는 대체로 좋다. Supabase/JWT fallback 인증, owner_user_id 조인, credential secret encryption, redaction values 수집이 보인다.

다만 Agent tool 경로에 provider token context를 넣는 구조는 side-effect 통제뿐 아니라 prompt/log redaction 부담도 키운다. 보안 관점에서도 Execution Action 쪽으로 수렴시키는 것이 더 안전하다.

### 9. 신뢰성, 관측성 및 오류 처리

run events, state snapshots, stale run recovery, websocket stream, semantic event writer가 있어 관측성 기반은 있다. 실패 이벤트도 user-safe error로 변환하려는 흐름이 있다.

현재 약점은 테스트 실패가 관측성 경로에 몰려 있다는 점이다. `crew_started`, event bridge output, callback redaction event가 기대대로 기록되는지 테스트가 깨져 있어 런타임 디버깅 신뢰도를 낮춘다.

### 10. 성능 및 비용 최적화

LLM catalog와 provider credential model은 비용 제어 기반이다. 하지만 비용 최적화의 핵심은 graph-level control이다. Agent loop 안에서 provider tool call이 발생하면 호출 횟수와 output count를 구조적으로 제한하기 어렵다.

단기 최적화는 prompt tuning이 아니라 graph architecture 전환이다. typed output schema와 Execution Action node를 더 적극적으로 써야 한다.

### 11. 테스트 및 검증

검증 결과:

- `npm run typecheck`: 통과.
- `npm test`: 실패. 46개 파일 중 3개 실패, 344개 테스트 중 6개 실패.
- `uv run pytest -q`: 실패. 1015개 통과, 1개 skip, 10개 실패.
- OpenAPI 비교: 통과. `docs/openapi.json`과 `app.openapi()`가 동일하고 path 수는 50개로 같다.

실패 테스트는 단순한 사소함으로 넘기기 어렵다. 프론트 실패는 agent contract mapping, mutation method expectation, invalidation count, HITL/Crew modal behavior를 가리킨다. 백엔드 실패는 runtime crew execution/event bridge/redaction/knowledge SQL path를 가리킨다.

## 권장 작업 순서

1. 테스트 기준선 복구
   - 먼저 실패 테스트가 "코드 버그"인지 "테스트 기대치 drift"인지 분류한다.
   - backend SQL path 실패는 테스트 실행 위치 문제로 보이므로 path 기준을 repo root 또는 backend root 중 하나로 통일한다.

2. Side-effect Agent tool 축소
   - Instagram publish는 기존 Execution Action 경로로 수렴한다.
   - Google Sheets write는 Execution Action 또는 static node로 분리하고 Agent tool에서는 read-only만 허용한다.

3. Runtime executor 분리
   - `execution_action` branch와 `crew` branch를 별도 executor로 추출한다.
   - credential/redaction context resolver를 공통 helper로 분리한다.

4. Frontend API contract 정리
   - graph API wrapper를 generated `paths` 타입으로 전환한다.
   - `as never` 사용 목록을 문서화하고 줄인다.

5. Cleanup candidates 실제 처리
   - orphan file 삭제 또는 archive.
   - cache 파일 정리.
   - god-file 분리 계획을 `docs/superpowers/plans`에 작성.

## 다음 기능 추가 전 체크리스트

- 새 외부 provider는 Agent tool이 아니라 Execution Action/static node인가?
- downstream routing에 필요한 값이 Task output schema로 정의되어 있는가?
- publish snapshot만으로 실행 가능한가?
- frontend API wrapper가 generated OpenAPI 타입을 쓰는가?
- owner_user_id, credential scope, redaction test가 있는가?
- 실패 이벤트가 run event/state snapshot에 남는가?
- 테스트 스위트가 현재 기준선에서 녹색인가?
