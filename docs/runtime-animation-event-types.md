# Runtime Animation Event Types

이 문서는 Home/Run 화면의 Pixi 애니메이션 레이어가 `FlowRun` 실시간 이벤트를 소비하기 위한 프론트엔드 타입 명세다.

## Transport

Run 이벤트 스트림은 WebSocket으로 전달된다.

```ts
const url = flowRunStreamUrl(runId); // /api/flow-runs/:runId/stream
const socket = new WebSocket(url);

socket.onopen = () => {
  socket.send(JSON.stringify({ type: 'authenticate', access_token }));
};

socket.onmessage = (message) => {
  const event = JSON.parse(message.data) as RuntimeAnimationEvent;
};
```

현재 `useFlowRunStream`은 다음 계약을 제공한다.

```ts
type FlowRunStreamOptions = {
  runId: string | undefined;
  enabled: boolean;
  onEvent?: (event: Record<string, unknown>) => void;
  onHitlRequested: () => void;
};
```

`onEvent`는 JSON parse 직후 호출된다. `hitl_requested` 중복 방지는 기존 `onHitlRequested`에만 적용되므로, 애니메이션 레이어에서 중복 방지가 필요하면 `event_id` 기준으로 한 번 더 dedupe한다.

활성 스트림 상태는 `running`, `executing`, `waiting_for_human`이다.

## Common Envelope

WebSocket 응답은 DB payload에 아래 필드를 보강한다. 일부 과거 이벤트는 payload 안에 `type`이 없을 수 있지만, 스트림 응답에서는 `event_type`으로부터 `type`이 채워진다.

```ts
type RuntimeEventType =
  | 'run_started'
  | 'run_completed'
  | 'run_failed'
  | 'crew_started'
  | 'crew_retry_started'
  | 'crew_completed'
  | 'crew_failed'
  | 'task_started'
  | 'task_completed'
  | 'task_failed'
  | 'agent_started'
  | 'agent_final_answer'
  | 'agent_failed'
  | 'tool_execution_started'
  | 'tool_execution_completed'
  | 'tool_execution_failed'
  | 'collaboration_started'
  | 'collaboration_completed'
  | 'collaboration_failed'
  | 'hitl_requested'
  | 'hitl_resolved'
  | 'run_rejected';

type RuntimeEventBase<TType extends RuntimeEventType = RuntimeEventType> = {
  type: TType;
  event_id: string;
  created_at: string;
  run_id: string;
  node_id: string | null;
};
```

프론트에서는 알 수 없는 `type`이 와도 무시하거나 Raw timeline에만 표시해야 한다. CrewAI/AX 이벤트는 앞으로 추가될 수 있다.

## Run Events

```ts
type RunStartedEvent = RuntimeEventBase<'run_started'> & {
  flow_version_id?: string;
};

type RunCompletedEvent = RuntimeEventBase<'run_completed'> & {
  output?: unknown;
};

type RunFailedEvent = RuntimeEventBase<'run_failed'> & {
  error_message: string;
  error?: string;
  fatal?: boolean;
  interrupted?: boolean;
};

type RunRejectedEvent = RuntimeEventBase<'run_rejected'> & {
  request_id: string;
  feedback: string;
};
```

Animation hint:

`run_started`는 전체 무대 진입, `run_completed`는 완료 연출, `run_failed`는 실패 상태 고정, `run_rejected`는 사용자 거절 종료 연출로 매핑한다.

## Crew Node Events

```ts
type CrewStartedEvent = RuntimeEventBase<'crew_started'> & {
  inputs?: unknown;
};

type CrewRetryStartedEvent = RuntimeEventBase<'crew_retry_started'> & {
  inputs?: unknown;
};

type CrewCompletedEvent = RuntimeEventBase<'crew_completed'> & {
  output?: unknown;
};

type CrewFailedEvent = RuntimeEventBase<'crew_failed'> & {
  error_message: string;
  fatal: true;
};
```

Animation hint:

`crew_started`는 Crew 노드/방 입장, `crew_retry_started`는 HITL 피드백 후 재작업, `crew_completed`는 Crew 결과 제출, `crew_failed`는 해당 Crew 노드 실패 연출로 쓰면 된다.

## Task Events

```ts
type TaskStartedEvent = RuntimeEventBase<'task_started'> & {
  task_id?: string;
  task_name?: string;
};

type TaskCompletedEvent = RuntimeEventBase<'task_completed'> & {
  task_id?: string;
  task_name?: string;
  output_preview?: string;
};

type TaskFailedEvent = RuntimeEventBase<'task_failed'> & {
  task_id?: string;
  task_name?: string;
  error_message: string;
  fatal: true;
};
```

Animation hint:

Task는 agent 행동의 상위 맥락이다. `task_started`에서 목표 말풍선/작업 카드 생성, `task_completed`에서 작업 카드 체크, `task_failed`에서 작업 카드 실패 처리를 권장한다.

## Agent Events

```ts
type AgentStartedEvent = RuntimeEventBase<'agent_started'> & {
  agent_id?: string;
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  task_prompt_preview?: string;
};

type AgentFinalAnswerEvent = RuntimeEventBase<'agent_final_answer'> & {
  agent_id?: string;
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  output_preview?: string;
};

type AgentFailedEvent = RuntimeEventBase<'agent_failed'> & {
  agent_id?: string;
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  error_message: string;
  fatal: true;
};
```

Animation hint:

`agent_started`는 캐릭터 활성화, `agent_final_answer`는 캐릭터가 결과를 말하거나 문서를 넘기는 동작, `agent_failed`는 해당 캐릭터 실패 상태로 매핑한다.

## Tool Execution Events

일반 Tool 사용 이벤트다. 협업 도구는 아래 `Collaboration Events`로 분리되어 들어온다.

```ts
type ToolExecutionStartedEvent = RuntimeEventBase<'tool_execution_started'> & {
  activity_kind: 'tool';
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  tool_name: string;
  tool_args_preview: unknown;
};

type ToolExecutionCompletedEvent = RuntimeEventBase<'tool_execution_completed'> & {
  activity_kind: 'tool';
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  tool_name: string;
  tool_args_preview: unknown;
  output_preview?: string;
};

type ToolExecutionFailedEvent = RuntimeEventBase<'tool_execution_failed'> & {
  activity_kind: 'tool';
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  tool_name: string;
  tool_args_preview: unknown;
  error_message: string;
  fatal?: boolean;
};
```

Animation hint:

Tool 이벤트는 캐릭터가 도구를 꺼내 쓰는 짧은 액션으로 매핑한다. 예: 검색 도구, 파일 도구, 내부 API 호출 등.

## Collaboration Events

CrewAI 내장 협업 도구는 일반 tool event에서 분리된다.

분리 기준:

- `ask_question_to_coworker`, `Ask Question To Coworker`, `AskQuestionTool`
- `delegate_work_to_coworker`, `Delegate Work To Coworker`, `DelegateWorkTool`
- 또는 tool args shape가 협업 도구 형태일 때
  - 질문: `question`, `context`, `coworker`
  - 위임: `task`, `context`, `coworker`

```ts
type CollaborationKind = 'ask_question' | 'delegate_work';

type CollaborationStartedEvent = RuntimeEventBase<'collaboration_started'> & {
  activity_kind: 'collaboration';
  collaboration_kind: CollaborationKind;
  raw_tool_name: string;
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  from_agent_role?: string;
  to_agent_role?: string;
  question?: string;
  task?: string;
  context_preview?: string;
};

type CollaborationCompletedEvent = RuntimeEventBase<'collaboration_completed'> & {
  activity_kind: 'collaboration';
  collaboration_kind: CollaborationKind;
  raw_tool_name: string;
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  from_agent_role?: string;
  to_agent_role?: string;
  question?: string;
  task?: string;
  context_preview?: string;
  output_preview?: string;
};

type CollaborationFailedEvent = RuntimeEventBase<'collaboration_failed'> & {
  activity_kind: 'collaboration';
  collaboration_kind: CollaborationKind;
  raw_tool_name: string;
  agent_role?: string;
  task_id?: string;
  task_name?: string;
  from_agent_role?: string;
  to_agent_role?: string;
  question?: string;
  task?: string;
  context_preview?: string;
  error_message: string;
  fatal?: boolean;
};
```

Animation hint:

`ask_question`은 Agent A가 Agent B에게 질문하는 모션, `delegate_work`는 Agent A가 Agent B에게 작업 묶음을 넘기는 모션으로 분리한다. 둘 다 `from_agent_role`과 `to_agent_role`이 있으면 캐릭터 간 연결선을 그릴 수 있다.

## HITL Events

HITL은 사용자 의사 결정 팝업과 연결된다. 현재 Run 페이지에서 처리하지만, Home에서도 같은 이벤트를 보고 공용 `HumanFeedbackDialog`를 띄울 수 있다.

```ts
type HitlRequestedEvent = RuntimeEventBase<'hitl_requested'> & {
  request_id: string;
  source_node_id: string;
  next_node_id: string | null;
  message: string;
  preview_payload_ref?: string;
  retry_count: number;
  max_attempts: number;
  remaining_retries: number;
};

type HitlResolvedEvent = RuntimeEventBase<'hitl_resolved'> & {
  request_id: string;
  outcome: 'approved' | 'needs_revision' | 'rejected';
  feedback: string;
};
```

Animation hint:

`hitl_requested`는 전체 흐름을 멈추고 사용자 판단 모달을 띄운다. `hitl_resolved`는 승인/재시도/거절 결과를 애니메이션 상태로 반영한다. `needs_revision`이면 보통 `crew_retry_started`가 뒤따른다.

## Full Union

```ts
type RuntimeAnimationEvent =
  | RunStartedEvent
  | RunCompletedEvent
  | RunFailedEvent
  | RunRejectedEvent
  | CrewStartedEvent
  | CrewRetryStartedEvent
  | CrewCompletedEvent
  | CrewFailedEvent
  | TaskStartedEvent
  | TaskCompletedEvent
  | TaskFailedEvent
  | AgentStartedEvent
  | AgentFinalAnswerEvent
  | AgentFailedEvent
  | ToolExecutionStartedEvent
  | ToolExecutionCompletedEvent
  | ToolExecutionFailedEvent
  | CollaborationStartedEvent
  | CollaborationCompletedEvent
  | CollaborationFailedEvent
  | HitlRequestedEvent
  | HitlResolvedEvent;
```

## Suggested Frontend Handler

```ts
function handleRuntimeAnimationEvent(event: RuntimeAnimationEvent) {
  switch (event.type) {
    case 'crew_started':
      return startCrewMotion(event.node_id, event.inputs);
    case 'task_started':
      return showTaskCard(event.node_id, event.task_name);
    case 'agent_started':
      return activateAgent(event.node_id, event.agent_role);
    case 'tool_execution_started':
      return playToolMotion(event.node_id, event.agent_role, event.tool_name);
    case 'collaboration_started':
      return playCollaborationMotion({
        from: event.from_agent_role,
        to: event.to_agent_role,
        kind: event.collaboration_kind,
      });
    case 'agent_final_answer':
      return showFinalAnswer(event.node_id, event.agent_role, event.output_preview);
    case 'hitl_requested':
      return openHumanFeedbackDialog(event.request_id);
    case 'run_completed':
      return completeRun(event.run_id);
    case 'run_failed':
    case 'crew_failed':
    case 'task_failed':
    case 'agent_failed':
    case 'tool_execution_failed':
    case 'collaboration_failed':
      return failMotion(event);
    default:
      return undefined;
  }
}
```

## MVP Failure Policy

MVP에서는 복구 로직을 구현하지 않고 실패 이벤트를 명시적으로 전달한다.

- Task 실패: `task_failed`
- Agent 실패: `agent_failed`
- Tool 실패: `tool_execution_failed`
- Collaboration 실패: `collaboration_failed`
- Crew 실패: `crew_failed`
- Run 실패: `run_failed`
- 사용자 거절: `run_rejected`
- 서버 재시작 등으로 끊긴 실행: `run_failed` with `interrupted: true`

고도화 단계에서 worker lease/heartbeat 기반 복구를 추가하면 `interrupted` 처리 정책을 다시 조정한다.

