import { expect, test } from 'vitest';
import { buildStreamingScene } from './streamingEventModel';

test('buildStreamingScene creates agents only from agent_started events in creation order', () => {
  const events = [
    {
      event_type: 'agent_step',
      created_at: '2026-05-02T12:00:00Z',
      event_payload_json: { agent_id: 'agent-a', agent_name: 'Agent A', thought: 'working on task' },
      node_id: 'node-1',
    },
    {
      event_type: 'agent_started',
      created_at: '2026-05-02T12:00:01Z',
      event_payload_json: { agent_id: 'agent-a', agent_name: 'Agent A' },
      node_id: 'node-1',
    },
    {
      event_type: 'agent_started',
      created_at: '2026-05-02T12:00:02Z',
      event_payload_json: { agent_id: 'agent-b', agent_name: 'Agent B' },
      node_id: 'node-2',
    },
    {
      event_type: 'agent_started',
      created_at: '2026-05-02T12:00:03Z',
      event_payload_json: { agent_id: 'agent-c', agent_name: 'Agent C' },
      node_id: 'node-3',
    },
    {
      event_type: 'agent_started',
      created_at: '2026-05-02T12:00:04Z',
      event_payload_json: { agent_id: 'agent-d', agent_name: 'Agent D' },
      node_id: 'node-4',
    },
    {
      event_type: 'agent_started',
      created_at: '2026-05-02T12:00:05Z',
      event_payload_json: { agent_id: 'agent-e', agent_name: 'Agent E' },
      node_id: 'node-5',
    },
  ];

  const scene = buildStreamingScene(events, false);

  expect(scene.agents.map((agent) => agent.name)).toEqual(['Agent A', 'Agent B', 'Agent C', 'Agent D', 'Agent E']);
  expect(scene.agents.map((agent) => agent.createdOrder)).toEqual([0, 1, 2, 3, 4]);
  expect(scene.agents.map((agent) => agent.motionIndex)).toEqual([1, 2, 3, 4, 1]);
  expect(scene.agents.map((agent) => agent.station)).toEqual([0, 1, 2, 3, 4]);
});

test('collaboration completion marks the target collaborator done', () => {
  const scene = buildStreamingScene(
    [
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:00Z',
        event_payload_json: { agent_id: 'main-agent', agent_name: 'Main Agent', agent_role: 'PM Agent' },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-02T12:00:01Z',
        event_payload_json: {
          from_agent_role: 'PM Agent',
          to_agent_role: 'Research Agent',
          task: 'research',
        },
      },
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:02Z',
        event_payload_json: { agent_id: 'research-agent-id', agent_name: 'Research Agent', agent_role: 'Research Agent' },
      },
      {
        event_type: 'collaboration_completed',
        created_at: '2026-05-02T12:00:03Z',
        event_payload_json: {
          from_agent_role: 'PM Agent',
          to_agent_role: 'Research Agent',
        },
      },
    ],
    false,
  );

  expect(scene.agents.map((agent) => [agent.name, agent.status])).toEqual([
    ['Main Agent', 'working'],
    ['Research Agent', 'done'],
  ]);
});

test('collaboration completion matches the target role while other collaborations stay active', () => {
  const baseEvents = [
    {
      event_type: 'agent_started',
      created_at: '2026-05-02T12:00:00Z',
      event_payload_json: { agent_id: 'main-agent', agent_name: 'Main Agent', agent_role: 'PM Agent' },
    },
    {
      event_type: 'collaboration_started',
      created_at: '2026-05-02T12:00:01Z',
      event_payload_json: {
        from_agent_role: 'PM Agent',
        to_agent_role: 'Arabic Agent',
      },
    },
    {
      event_type: 'collaboration_started',
      created_at: '2026-05-02T12:00:02Z',
      event_payload_json: {
        from_agent_role: 'PM Agent',
        to_agent_role: 'American Agent',
      },
    },
    {
      event_type: 'collaboration_completed',
      created_at: '2026-05-02T12:00:03Z',
      event_payload_json: {
        from_agent_role: 'PM Agent',
        to_agent_role: 'American Agent',
      },
    },
  ];

  const afterAmericanDone = buildStreamingScene(baseEvents, false);
  expect(afterAmericanDone.agents.map((agent) => [agent.name, agent.status])).toEqual([
    ['Main Agent', 'meeting'],
    ['Arabic Agent', 'meeting'],
    ['American Agent', 'done'],
  ]);

  const afterArabicDone = buildStreamingScene(
    [
      ...baseEvents,
      {
        event_type: 'collaboration_completed',
        created_at: '2026-05-02T12:00:04Z',
        event_payload_json: {
          from_agent_role: 'PM Agent',
          to_agent_role: 'Arabic Agent',
        },
      },
    ],
    false,
  );
  expect(afterArabicDone.agents.map((agent) => [agent.name, agent.status])).toEqual([
    ['Main Agent', 'working'],
    ['Arabic Agent', 'done'],
    ['American Agent', 'done'],
  ]);
});

test('agent final answer does not finish a collaborator before its collaboration completes', () => {
  const scene = buildStreamingScene(
    [
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:00Z',
        event_payload_json: { agent_id: 'main-agent', agent_name: 'Main Agent', agent_role: 'PM Agent' },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-02T12:00:01Z',
        event_payload_json: {
          from_agent_role: 'PM Agent',
          to_agent_role: 'Arabic Agent',
        },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-02T12:00:02Z',
        event_payload_json: {
          from_agent_role: 'PM Agent',
          to_agent_role: 'American Agent',
        },
      },
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:03Z',
        event_payload_json: {
          agent_id: 'american-agent-id',
          agent_name: 'American Agent',
          agent_role: 'American Agent',
        },
      },
      {
        event_type: 'agent_final_answer',
        created_at: '2026-05-02T12:00:04Z',
        event_payload_json: {
          agent_id: 'american-agent-id',
          agent_role: 'American Agent',
        },
      },
    ],
    false,
  );

  expect(scene.agents.map((agent) => [agent.name, agent.status])).toEqual([
    ['Main Agent', 'meeting'],
    ['Arabic Agent', 'meeting'],
    ['American Agent', 'meeting'],
  ]);
});

test('agent_started updates an existing role-created collaborator without creating a new agent', () => {
  const scene = buildStreamingScene(
    [
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:00Z',
        event_payload_json: { agent_id: 'main-agent', agent_name: 'Main Agent', agent_role: 'PM Agent' },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-02T12:00:01Z',
        event_payload_json: {
          from_agent_role: 'PM Agent',
          to_agent_role: 'Research Agent',
          task: 'research',
        },
      },
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:02Z',
        event_payload_json: {
          agent_id: 'runtime-research-agent-id',
          agent_name: 'Research Agent',
          agent_role: 'Research Agent',
          goal: 'Find evidence',
        },
      },
    ],
    false,
  );

  expect(scene.agents).toHaveLength(2);
  expect(scene.agents.map((agent) => [agent.id, agent.name, agent.status])).toEqual([
    ['main-agent', 'Main Agent', 'meeting'],
    ['research-agent', 'Research Agent', 'meeting'],
  ]);
  expect(scene.agents[1].meta?.versionId).toBe('runtime-research-agent-id');
  expect(scene.agents[1].meta?.goal).toBe('Find evidence');
});

test('collaboration_started creates distinct temporary agents for Korean role names without agent_started', () => {
  const scene = buildStreamingScene(
    [
      {
        event_type: 'agent_started',
        created_at: '2026-05-05T01:40:30Z',
        event_payload_json: {
          agent_id: 'korean-runtime-id',
          agent_role: '한국인 에이전트',
        },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-05T01:40:36Z',
        event_payload_json: {
          from_agent_role: '한국인 에이전트',
          to_agent_role: '아랍인 에이전트',
          question: '아랍 국가 AI 사용 사례를 알려주세요.',
        },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-05T01:40:37Z',
        event_payload_json: {
          from_agent_role: '한국인 에이전트',
          to_agent_role: '영국인 에이전트',
          question: '법적 윤리적 관점도 알려주세요.',
        },
      },
    ],
    false,
  );

  expect(scene.agents.map((agent) => [agent.id, agent.name, agent.status])).toEqual([
    ['korean-runtime-id', '한국인 에이전트', 'meeting'],
    ['아랍인-에이전트', '아랍인 에이전트', 'meeting'],
    ['영국인-에이전트', '영국인 에이전트', 'meeting'],
  ]);
});

test('participant-less collaboration events do not pull every known agent into meeting', () => {
  const scene = buildStreamingScene(
    [
      {
        event_type: 'agent_started',
        created_at: '2026-05-06T00:31:07Z',
        event_payload_json: {
          agent_id: 'runtime-agent-1',
          agent_name: 'Agent 1',
          agent_role: 'Agent 1',
        },
      },
      {
        event_type: 'agent_started',
        created_at: '2026-05-06T00:31:11Z',
        event_payload_json: {
          agent_id: 'runtime-agent-2',
          agent_name: 'Agent 2',
          agent_role: 'Agent 2',
        },
      },
      {
        event_type: 'agent_started',
        created_at: '2026-05-06T00:31:27Z',
        event_payload_json: {
          agent_id: 'runtime-agent-3',
          agent_name: 'Agent 3',
          agent_role: 'Agent 3',
        },
      },
      {
        event_type: 'collaboration_started',
        created_at: '2026-05-06T00:31:43Z',
        event_payload_json: {},
      },
      {
        event_type: 'collaboration_completed',
        created_at: '2026-05-06T00:31:57Z',
        event_payload_json: {},
      },
    ],
    false,
    ['Agent 1', 'Agent 2', 'Agent 3'],
  );

  expect(scene.agents.map((agent) => [agent.name, agent.status])).toEqual([
    ['Agent 1', 'working'],
    ['Agent 2', 'working'],
    ['Agent 3', 'working'],
  ]);
});

test('flow completion freezes all runtime agents', () => {
  const scene = buildStreamingScene(
    [
      {
        event_type: 'agent_started',
        created_at: '2026-05-02T12:00:00Z',
        event_payload_json: { agent_id: 'main-agent', agent_name: 'Main Agent' },
      },
      {
        event_type: 'run_completed',
        created_at: '2026-05-02T12:00:01Z',
        event_payload_json: { output: {} },
      },
    ],
    false,
  );

  expect(scene.agents).toHaveLength(1);
  expect(scene.agents[0].isFlowComplete).toBe(true);
});
