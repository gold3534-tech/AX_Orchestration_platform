# AX Orchestration Platform

AX Orchestration Platform은 AI Agent, Task, Crew, Flow를 시각적으로 구성하고 실행할 수 있는 풀스택 AI 워크플로우 오케스트레이션 플랫폼입니다. 사용자는 화면에서 Agent와 Task를 만들고, Crew와 Flow 그래프를 연결한 뒤, 발행된 Flow를 실행하면서 진행 상태와 결과를 확인할 수 있습니다.

이 저장소는 이력서 및 포트폴리오 제출을 위해 정리한 public 버전입니다. 실제 운영용 비밀값, 로컬 환경, 빌드 산출물, 내부 작업 로그는 포함하지 않았습니다.

## 데모 영상

[Home에서 Flow를 실행했을 때 애니메이션이 동작하는 모습 보기](docs/media/ax-platform-demo.mp4)

## 주요 화면

### 실행 화면

발행된 Flow를 선택하고 실행 입력값을 넣어 워크플로우 실행을 시작하는 화면입니다.

![실행 화면](docs/media/home-runner.png)

### Home - 2D 실행 시각화 화면

Home 화면에서 실행 중인 Flow의 진행 과정을 2D 그래픽 애니메이션으로 볼 수 있습니다.

![Home 2D 실행 시각화 화면](docs/media/flow-builder.png)

### Agent 생성 탭

워크플로우에서 사용할 Agent를 생성하고 관리하는 화면입니다.

![Agent 생성 탭](docs/media/crew-builder.png)

### Task 생성 탭

Agent에게 할당할 Task를 생성하고, 설명과 기대 출력값을 관리하는 화면입니다.

![Task 생성 탭](docs/media/run-launcher.png)

### Flow 생성 탭

여러 Crew와 실행 노드를 연결해 전체 워크플로우 Flow를 구성하는 화면입니다.

![Flow 생성 탭](docs/media/agents-library.png)

### Crew 생성 탭

Agent와 Task를 연결해 실행 가능한 Crew 단위를 구성하는 그래프 빌더 화면입니다.

![Crew 생성 탭](docs/media/tasks-library.png)

## 핵심 기능

- Agent, Task, Crew, Flow를 버전 기반 asset으로 생성 및 관리
- Crew Builder와 Flow Builder를 통한 그래프 기반 워크플로우 구성
- Draft graph 저장, 검증, 발행 및 runtime snapshot 생성
- 발행된 Flow 실행과 실행 이벤트 스트리밍
- Human-in-the-loop 검토 게이트, 실행 액션, 산출물 처리
- Knowledge/RAG 연동을 위한 지식 자산 관리
- OpenAPI 기반 frontend/backend 타입 계약 관리

## 시스템 흐름

```text
Agent / Task 생성
-> Crew 그래프 구성
-> Flow 그래프 구성
-> Draft 저장 및 Publish
-> Runtime snapshot 생성
-> Flow 실행
-> 실행 이벤트 / 산출물 / 결과 확인
```

## 기술 스택

- Frontend: React, TypeScript, Vite, TanStack Query, React Flow, PixiJS
- Backend: Python, FastAPI, SQLAlchemy, Pydantic
- Runtime: CrewAI 스타일 Agent/Task orchestration, graph loader, run event pipeline
- Data/API: versioned asset model, runtime snapshot, OpenAPI contract
- Test: frontend smoke tests, backend API/runtime tests

## 프로젝트 구조

```text
frontend/
  React 기반 화면, 빌더, 실행 페이지, 2D 시각화 UI

backend/
  FastAPI API 서버, graph publish/load, runtime execution, event pipeline

docs/
  OpenAPI 문서, 아키텍처 노트, 스크린샷, 데모 영상

data/
  예시 및 참고 데이터
```

## 주요 코드 위치

- [`frontend/src/features/agents`](frontend/src/features/agents): Agent 생성 및 관리 UI
- [`frontend/src/features/tasks`](frontend/src/features/tasks): Task 생성 및 관리 UI
- [`frontend/src/features/crews`](frontend/src/features/crews): Crew graph builder
- [`frontend/src/features/flows`](frontend/src/features/flows): Flow graph builder
- [`frontend/src/features/home`](frontend/src/features/home): Home 실행 화면 및 Pixi 기반 2D 시각화
- [`frontend/src/features/runs`](frontend/src/features/runs): Flow 실행, 이벤트 스트리밍, 결과 확인
- [`backend/api/routes`](backend/api/routes): FastAPI route layer
- [`backend/api/services`](backend/api/services): asset, graph, run, credential, knowledge 도메인 로직
- [`backend/api/runtime`](backend/api/runtime): runtime snapshot 실행, graph loader, event writer, artifact 처리

## 로컬 실행

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

외부 API, OAuth, DB 연결에 필요한 환경변수는 public 저장소에 포함하지 않았습니다. 실제 실행 시에는 각자 로컬 `.env` 파일을 만들어 설정해야 합니다.

## 테스트

```bash
cd frontend
npm test
```

```bash
cd backend
pytest
```

## Public 버전 정리 내역

- 실제 `.env` 파일 제거
- `.git`, 가상환경, `node_modules`, 캐시, 빌드 산출물 제거
- 내부 작업 계획 로그 제거
- GitHub Push Protection에 걸릴 수 있는 테스트용 secret-shaped 문자열 정리
- 포트폴리오용 스크린샷과 데모 영상 추가

공개 전 점검용 체크리스트는 [`PUBLIC_RELEASE_CHECKLIST.md`](PUBLIC_RELEASE_CHECKLIST.md)에 정리했습니다.
