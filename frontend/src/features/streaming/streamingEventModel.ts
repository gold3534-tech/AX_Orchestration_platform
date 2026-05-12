import type { AgentSceneModel, AgentSceneStatus, SceneLogLine, StreamEvent } from './streamingTypes';

function stringValue(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function payloadRecord(event: StreamEvent): Record<string, unknown> {
  const payload = event.event_payload_json;
  return payload !== null && typeof payload === 'object' && !Array.isArray(payload) ? (payload as Record<string, unknown>) : {};
}

function eventId(event: StreamEvent, index: number) {
  return stringValue(event, 'id') ?? `${index}`;
}

function eventType(event: StreamEvent) {
  return stringValue(event, 'event_type') ?? 'event';
}

function eventTime(event: StreamEvent) {
  return stringValue(event, 'created_at') ?? '';
}

function readableEventType(type: string) {
  const titles: Record<string, string> = {
    agent_step: 'Agent step',
    agent_tool_result: 'Tool result',
    agent_finish: 'Agent finish',
    agent_final_answer: 'Agent final answer',
    task_started: 'Task started',
    task_completed: 'Task completed',
    collaboration_started: 'Collaboration started',
    collaboration_completed: 'Collaboration completed',
    telemetry_error: 'Telemetry error',
    run_started: 'Run started',
    crew_started: 'Crew started',
    crew_completed: 'Crew completed',
    run_completed: 'Run completed',
  };

  return titles[type] ?? type;
}

function explicitAgentNameFromEvent(event: StreamEvent): string | null {
  const payload = payloadRecord(event);
  return stringValue(payload, 'agent_name') ?? stringValue(payload, 'agent') ?? stringValue(payload, 'agent_role') ?? null;
}

function messageFromEvent(event: StreamEvent) {
  const payload = payloadRecord(event);
  return (
    stringValue(payload, 'thought') ??
    stringValue(payload, 'result') ??
    stringValue(payload, 'output') ??
    stringValue(payload, 'output_preview') ??
    stringValue(payload, 'message') ??
    stringValue(payload, 'question') ??
    stringValue(payload, 'task') ??
    readableEventType(eventType(event))
  );
}

function colorFromString(value: string, palette: number[]) {
  let hash = 0;
  for (const char of value) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
}

function normalizedId(value: string) {
  const normalized = value
    .normalize('NFKC')
    .replace(/[^\p{L}\p{N}-]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
  return normalized || 'agent';
}

function createAgent(id: string, name: string, station: number, lastMessage: string): AgentSceneModel {
  return {
    id,
    name,
    status: 'idle',
    station,
    lastMessage,
    parts: {
      hair: colorFromString(id, [0x4a2d23, 0x2f2a2a, 0x8d5a2f, 0x6a4b38]),
      top: colorFromString(`${id}:top`, [0x3d7dd8, 0x5bbf8a, 0xd85f5f, 0x8e6ee8, 0xe0a23a]),
      bottom: colorFromString(`${id}:bottom`, [0x2f3a52, 0x3f4f3f, 0x684a62, 0x6d5847]),
      face: colorFromString(`${id}:face`, [0xffd4a3, 0xe8aa76, 0xc9815a, 0xf0c49b]),
    },
  };
}

function statusFromEventType(type: string): AgentSceneStatus {
  if (type.includes('failed') || type.includes('error')) return 'blocked';
  if (type === 'agent_final_answer' || type === 'agent_finish') return 'done';
  if (type === 'collaboration_started') return 'meeting';
  if (type === 'collaboration_completed') return 'working';
  if (type === 'agent_started' || type.includes('tool')) return 'working';
  return 'idle';
}

export function buildStreamingScene(events: StreamEvent[], waitingForHuman: boolean, knownAgentNames: string[] = []) {
  const agents = new Map<string, AgentSceneModel>();
  const logs: SceneLogLine[] = [];
  const createdAgentIds: string[] = [];
  const roleToAgentId = new Map<string, string>();
  const rawIdToAgentId = new Map<string, string>();
  const activeCollaborations = new Map<string, number>();
  const knownCollaboratorNames = knownAgentNames.map((name) => name.trim()).filter(Boolean);
  let isFlowComplete = false;

  function roleKey(value: string | null | undefined) {
    return value ? value.replace(/[-_:]+/g, ' ').trim().toLowerCase() : null;
  }

  function resolveAgentId(value: string | null) {
    if (!value) return null;
    const normalized = normalizedId(value);
    return rawIdToAgentId.get(normalized) ?? normalized;
  }

  function mergeAgentIds(fromId: string, intoId: string) {
    if (fromId === intoId) return;
    const existing = agents.get(fromId);
    const target = agents.get(intoId);
    if (existing && target) {
      target.lastMessage = existing.lastMessage || target.lastMessage;
      target.meta = { ...existing.meta, ...target.meta };
      target.hasEnteredMeeting = target.hasEnteredMeeting || existing.hasEnteredMeeting;
      agents.delete(fromId);
    } else if (existing && !target) {
      agents.delete(fromId);
      existing.id = intoId;
      agents.set(intoId, existing);
    }

    const existingCollaborationCount = activeCollaborations.get(fromId);
    if (existingCollaborationCount !== undefined) {
      activeCollaborations.delete(fromId);
      activeCollaborations.set(intoId, (activeCollaborations.get(intoId) ?? 0) + existingCollaborationCount);
    }
    const orderIndex = createdAgentIds.indexOf(fromId);
    if (orderIndex >= 0 && !createdAgentIds.includes(intoId)) createdAgentIds[orderIndex] = intoId;
    else if (orderIndex >= 0) createdAgentIds.splice(orderIndex, 1);
  }

  function ensureAgent(rawId: string, name: string, lastMessage: string, role?: string | null) {
    const key = roleKey(role) ?? roleKey(name);
    const normalizedRawId = normalizedId(rawId);
    const existingIdForRole = key ? roleToAgentId.get(key) : undefined;
    const existingIdForRaw = rawIdToAgentId.get(normalizedRawId);
    const id = existingIdForRole ?? existingIdForRaw ?? normalizedRawId;

    if (existingIdForRole && existingIdForRaw && existingIdForRole !== existingIdForRaw) mergeAgentIds(existingIdForRaw, existingIdForRole);
    if (key) {
      roleToAgentId.set(key, id);
    }
    rawIdToAgentId.set(normalizedRawId, id);

    if (!createdAgentIds.includes(id)) createdAgentIds.push(id);
    const createdOrder = createdAgentIds.indexOf(id);
    const agent = agents.get(id) ?? createAgent(id, name, createdOrder, lastMessage);
    agent.createdOrder = createdOrder;
    agent.motionIndex = (createdOrder % 4) + 1;
    agent.station = createdOrder;
    if (agent.name === id && name !== id) agent.name = name;
    return agent;
  }

  function setMetadata(agent: AgentSceneModel, payload: Record<string, unknown>, rawId: string, role?: string | null) {
    agent.meta = agent.meta ?? {};
    agent.meta.versionId = stringValue(payload, 'agent_id') ?? stringValue(payload, 'agent_version_id') ?? agent.meta.versionId ?? rawId;
    agent.meta.role =
      role ??
      stringValue(payload, 'agent_role') ??
      stringValue(payload, 'from_agent_role') ??
      stringValue(payload, 'to_agent_role') ??
      agent.meta.role ??
      null;
    agent.meta.details =
      stringValue(payload, 'agent_details') ?? stringValue(payload, 'agent_description') ?? agent.meta.details ?? null;
    agent.meta.goal = stringValue(payload, 'goal') ?? agent.meta.goal ?? null;
  }

  function updateExisting(rawId: string | null, status: AgentSceneStatus, message: string) {
    const id = resolveAgentId(rawId);
    if (!id) return;
    const agent = agents.get(id);
    if (!agent) return;
    agent.status = status;
    agent.lastMessage = message;
    agents.set(id, agent);
  }

  function setCollaborationCount(agentId: string, delta: number) {
    const nextCount = Math.max(0, (activeCollaborations.get(agentId) ?? 0) + delta);
    if (nextCount === 0) activeCollaborations.delete(agentId);
    else activeCollaborations.set(agentId, nextCount);
    return nextCount;
  }

  function idFromRoleOrName(value: string | null) {
    const key = roleKey(value);
    return key ? roleToAgentId.get(key) ?? null : null;
  }

  function collaborationParticipantIds(payload: Record<string, unknown>) {
    const ids = [
      stringValue(payload, 'from_agent_id') ??
        stringValue(payload, 'agent_id') ??
        idFromRoleOrName(stringValue(payload, 'from_agent_role')) ??
        idFromRoleOrName(stringValue(payload, 'agent_name')),
      stringValue(payload, 'to_agent_id') ??
        idFromRoleOrName(stringValue(payload, 'to_agent_role')) ??
        idFromRoleOrName(stringValue(payload, 'coworker')) ??
        idFromRoleOrName(stringValue(payload, 'to_agent')),
    ].filter((value): value is string => Boolean(value));
    return Array.from(new Set(ids.map((id) => resolveAgentId(id) ?? normalizedId(id))));
  }

  function collaborationParticipantRefs(payload: Record<string, unknown>) {
    const fromId =
      stringValue(payload, 'from_agent_id') ??
      stringValue(payload, 'agent_id') ??
      idFromRoleOrName(stringValue(payload, 'from_agent_role')) ??
      idFromRoleOrName(stringValue(payload, 'agent_name'));
    const toId =
      stringValue(payload, 'to_agent_id') ??
      idFromRoleOrName(stringValue(payload, 'to_agent_role')) ??
      idFromRoleOrName(stringValue(payload, 'coworker')) ??
      idFromRoleOrName(stringValue(payload, 'to_agent'));

    return {
      fromId: resolveAgentId(fromId),
      toId: resolveAgentId(toId),
    };
  }

  events.forEach((event, index) => {
    const type = eventType(event);
    const payload = payloadRecord(event);
    const message = messageFromEvent(event);
    const explicit = explicitAgentNameFromEvent(event);
    const source = type.includes('agent') && explicit ? explicit : stringValue(payload, 'from_agent_role') ?? 'System';

    if (type === 'agent_started' && stringValue(payload, 'agent_id')) {
      const rawId = stringValue(payload, 'agent_id') as string;
      const name =
        stringValue(payload, 'agent_name') ?? stringValue(payload, 'agent') ?? stringValue(payload, 'agent_role') ?? rawId;
      const agent = ensureAgent(rawId, name, message, stringValue(payload, 'agent_role'));
      agent.status = (activeCollaborations.get(agent.id) ?? 0) > 0 ? 'meeting' : 'working';
      agent.lastMessage = message;
      setMetadata(agent, payload, rawId, stringValue(payload, 'agent_role'));
      agents.set(agent.id, agent);
    } else if (type === 'collaboration_started') {
      const participants = [
        {
          rawId: stringValue(payload, 'from_agent_id') ?? stringValue(payload, 'agent_id'),
          name: stringValue(payload, 'from_agent_name') ?? stringValue(payload, 'from_agent_role'),
          role: stringValue(payload, 'from_agent_role'),
        },
        {
          rawId: stringValue(payload, 'to_agent_id'),
          name:
            stringValue(payload, 'to_agent_name') ??
            stringValue(payload, 'to_agent_role') ??
            stringValue(payload, 'coworker') ??
            stringValue(payload, 'to_agent'),
          role: stringValue(payload, 'to_agent_role') ?? stringValue(payload, 'coworker') ?? stringValue(payload, 'to_agent'),
        },
      ].filter(({ rawId, name, role }) => Boolean(rawId ?? name ?? role));

      if (participants.length > 0 && participants.length < 2) {
        const existingKeys = new Set(
          participants
            .map(({ name, role }) => roleKey(role) ?? roleKey(name))
            .filter((value): value is string => Boolean(value)),
        );
        knownCollaboratorNames.forEach((name) => {
          const key = roleKey(name);
          if (!key || existingKeys.has(key)) return;
          participants.push({ rawId: null, name, role: name });
          existingKeys.add(key);
        });
      }

      participants.forEach(({ rawId, name, role }) => {
        const fallback = role ?? name;
        const resolvedId = rawId ?? idFromRoleOrName(role) ?? idFromRoleOrName(name) ?? fallback;
        if (!resolvedId) return;
        const agent = ensureAgent(resolvedId, name ?? fallback ?? 'Agent', message, role);
        setCollaborationCount(agent.id, 1);
        agent.status = 'meeting';
        agent.hasEnteredMeeting = true;
        agent.lastMessage = message;
        setMetadata(agent, payload, resolvedId, role);
        agents.set(agent.id, agent);
      });
    } else if (type === 'collaboration_completed' || type === 'collaboration_failed') {
      const { fromId, toId } = collaborationParticipantRefs(payload);
      if (fromId) {
        const remainingCollaborations = setCollaborationCount(fromId, -1);
        const nextStatus: AgentSceneStatus =
          type === 'collaboration_failed' ? 'blocked' : remainingCollaborations > 0 ? 'meeting' : 'working';
        updateExisting(fromId, nextStatus, message);
      }
      if (toId && toId !== fromId) {
        setCollaborationCount(toId, -1);
        updateExisting(toId, type === 'collaboration_failed' ? 'blocked' : 'done', message);
      }

      if (!fromId && !toId) {
        const status: AgentSceneStatus = type === 'collaboration_failed' ? 'blocked' : 'working';
        collaborationParticipantIds(payload).forEach((id) => {
          const remainingCollaborations = setCollaborationCount(id, -1);
          const nextStatus = remainingCollaborations > 0 && status !== 'blocked' ? 'meeting' : status;
          updateExisting(id, nextStatus, message);
        });
      }
    } else if (type === 'agent_final_answer' || type === 'agent_finish') {
      const rawId = stringValue(payload, 'agent_id');
      const id = resolveAgentId(rawId);
      updateExisting(rawId, id && (activeCollaborations.get(id) ?? 0) > 0 ? 'meeting' : 'done', message);
    } else if (type === 'run_completed' || type === 'crew_completed') {
      isFlowComplete = true;
    } else {
      const rawId = stringValue(payload, 'agent_id');
      if (rawId) {
        const id = resolveAgentId(rawId);
        if (!id) return;
        const existing = agents.get(id);
        if (existing) {
          existing.status = statusFromEventType(type);
          if ((activeCollaborations.get(id) ?? 0) > 0 && existing.status !== 'blocked') {
            existing.status = 'meeting';
          }
          existing.lastMessage = message;
          setMetadata(existing, payload, rawId, stringValue(payload, 'agent_role'));
          agents.set(id, existing);
        }
      }
    }

    logs.push({
      id: eventId(event, index),
      level: type.includes('error') || type.includes('failed') ? 'error' : type.includes('agent') ? 'agent' : waitingForHuman ? 'hitl' : 'system',
      timestamp: eventTime(event),
      source,
      message: stringValue(payload, 'tool') !== null ? `${message} | tool: ${stringValue(payload, 'tool')}` : message,
    });
  });

  if (waitingForHuman) {
    logs.push({
      id: 'hitl-waiting',
      level: 'hitl',
      timestamp: '',
      source: 'HITL',
      message: 'Human feedback is requested before the workflow can continue.',
    });
  }

  if (isFlowComplete) {
    agents.forEach((agent) => {
      agent.isFlowComplete = true;
    });
  }

  knownAgentNames.forEach((name) => {
    if (!name.trim()) return;
  });

  return {
    agents: Array.from(agents.values()),
    logs,
  };
}
