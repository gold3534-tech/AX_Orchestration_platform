import type { Connection } from '@xyflow/react';
import type { FlowGraphNodeId } from '../flowGraphTypes';
import type { FlowCanvasDraft, PublishedCrewOption } from '../hooks';

const CREW_FLOW_NODE_MIN_WIDTH = 560;
const CREW_FLOW_NODE_HEADER_WIDTH = 260;
const CREW_FLOW_NODE_STEP_WIDTH = 178;
const CREW_FLOW_NODE_HEIGHT = 300;

export type CrewStepSummary = {
  taskVersionId: string;
  taskName: string;
  agentName: string;
  toolKeys: string[];
  toolNames: string[];
  agentToolNames: string[];
  taskToolNames: string[];
};

export type OutputFieldOption = {
  value: string;
  label: string;
  nodeId: FlowGraphNodeId;
  path: string;
};

export type ResolvedCrewVisual = {
  name?: string;
  runtimeSnapshot?: Record<string, unknown>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown, fallback = '') {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function stringArrayFromRecord(record: Record<string, unknown>, key: string): string[] {
  return Array.isArray(record[key]) ? record[key].filter((value): value is string => typeof value === 'string') : [];
}

export function getCrewStepSummaries(runtimeSnapshot: unknown): CrewStepSummary[] {
  if (!isRecord(runtimeSnapshot)) {
    return [];
  }

  const runtimeCrew = isRecord(runtimeSnapshot.runtime_crew) ? runtimeSnapshot.runtime_crew : {};
  const runtimeTasks = isRecord(runtimeSnapshot.runtime_tasks) ? runtimeSnapshot.runtime_tasks : {};
  const runtimeAgents = isRecord(runtimeSnapshot.runtime_agents) ? runtimeSnapshot.runtime_agents : {};
  const taskAgentLinks = isRecord(runtimeSnapshot.task_agent_links) ? runtimeSnapshot.task_agent_links : {};
  const legacyToolLinks = isRecord(runtimeSnapshot.tool_links) ? runtimeSnapshot.tool_links : {};
  const agentToolLinks = isRecord(runtimeSnapshot.agent_tool_links) ? runtimeSnapshot.agent_tool_links : legacyToolLinks;
  const taskToolLinks = isRecord(runtimeSnapshot.task_tool_links) ? runtimeSnapshot.task_tool_links : {};
  const runtimeTools = isRecord(runtimeSnapshot.runtime_tools) ? runtimeSnapshot.runtime_tools : {};
  const taskVersionIds = Array.isArray(runtimeCrew.task_version_ids)
    ? runtimeCrew.task_version_ids.filter((value): value is string => typeof value === 'string')
    : [];

  return taskVersionIds.map((taskVersionId, index) => {
    const task = isRecord(runtimeTasks[taskVersionId]) ? runtimeTasks[taskVersionId] : {};
    const agentVersionId = typeof taskAgentLinks[taskVersionId] === 'string' ? taskAgentLinks[taskVersionId] : '';
    const agent = isRecord(runtimeAgents[agentVersionId]) ? runtimeAgents[agentVersionId] : {};
    const agentToolKeys = stringArrayFromRecord(agentToolLinks, agentVersionId);
    const taskToolKeys = [
      ...stringArrayFromRecord(legacyToolLinks, taskVersionId),
      ...stringArrayFromRecord(taskToolLinks, taskVersionId),
    ];
    const toolKeys = [...agentToolKeys];
    for (const toolKey of taskToolKeys) {
      if (!toolKeys.includes(toolKey)) {
        toolKeys.push(toolKey);
      }
    }
    const toolNames = toolKeys.map((toolKey) => {
      const tool = isRecord(runtimeTools[toolKey]) ? runtimeTools[toolKey] : {};
      return asString(tool.name, toolKey);
    });
    const agentToolNames = agentToolKeys.map((toolKey) => {
      const tool = isRecord(runtimeTools[toolKey]) ? runtimeTools[toolKey] : {};
      return asString(tool.name, toolKey);
    });
    const taskToolNames = toolNames;

    return {
      taskVersionId,
      taskName: asString(task.task_name, asString(task.name, `Task ${index + 1}`)),
      agentName: asString(agent.agent_name, asString(agent.name, 'Unassigned agent')),
      toolKeys,
      toolNames,
      agentToolNames,
      taskToolNames,
    };
  });
}

export function getCrewFlowNodeDimensions(runtimeSnapshot: unknown) {
  const stepCount = Math.max(getCrewStepSummaries(runtimeSnapshot).length, 1);
  return {
    width: Math.max(CREW_FLOW_NODE_MIN_WIDTH, CREW_FLOW_NODE_HEADER_WIDTH + stepCount * CREW_FLOW_NODE_STEP_WIDTH),
    height: CREW_FLOW_NODE_HEIGHT,
  };
}

function collectSchemaPaths(schema: unknown, prefix = ''): string[] {
  if (!isRecord(schema)) {
    return [];
  }

  const properties = isRecord(schema.properties) ? schema.properties : {};
  const paths: string[] = [];

  for (const [key, value] of Object.entries(properties)) {
    const path = prefix ? `${prefix}.${key}` : key;
    paths.push(path);
    if (isRecord(value) && value.type === 'object') {
      paths.push(...collectSchemaPaths(value, path));
    }
  }

  return paths;
}

export function resolveCrewVisual(
  versionId: string,
  draft: FlowCanvasDraft,
  publishedCrews: PublishedCrewOption[],
): ResolvedCrewVisual | undefined {
  const publishedCrew = publishedCrews.find((crew) => crew.versionId === versionId);
  if (publishedCrew) {
    return {
      name: publishedCrew.name,
      runtimeSnapshot: publishedCrew.runtimeSnapshot,
    };
  }

  const pinnedCrew = draft.entities?.crews?.[versionId];
  if (!isRecord(pinnedCrew)) {
    return undefined;
  }

  const runtimeSnapshot = isRecord(pinnedCrew.runtime_snapshot_json) ? pinnedCrew.runtime_snapshot_json : undefined;

  return {
    name: asString(pinnedCrew.name),
    runtimeSnapshot,
  };
}

export function getOutputFieldOptions(draft: FlowCanvasDraft, publishedCrews: PublishedCrewOption[]): OutputFieldOption[] {
  return draft.nodes.flatMap((node) => {
    if (node.type !== 'crew') {
      return [];
    }

    const versionId = typeof node.data.versionId === 'string' ? node.data.versionId : '';
    const crew = resolveCrewVisual(versionId, draft, publishedCrews);
    const outputSchema = isRecord(crew?.runtimeSnapshot) ? crew.runtimeSnapshot.output_schema : undefined;
    const paths = collectSchemaPaths(outputSchema);
    const crewName = crew?.name ?? node.id;
    const outputLabelPrefix = `${crewName} (${node.id})`;

    return [
      {
        value: `${node.id}|raw`,
        label: `${outputLabelPrefix} / raw`,
        nodeId: node.id,
        path: 'raw',
      },
      ...paths.map((path) => ({
        value: `${node.id}|json.${path}`,
        label: `${outputLabelPrefix} / json.${path}`,
        nodeId: node.id,
        path,
      })),
    ];
  });
}

export function connectFlowCanvasNodes(draft: FlowCanvasDraft, connection: Connection) {
  if (!connection.source || !connection.target || connection.source === connection.target) {
    return draft;
  }

  const source = connection.source as FlowGraphNodeId;
  const target = connection.target as FlowGraphNodeId;

  if (source.startsWith('tool:') || target.startsWith('tool:')) {
    return draft;
  }

  const hasExistingEdge = draft.edges.some((edge) => edge.source === source && edge.target === target && edge.type === 'flow');

  if (hasExistingEdge) {
    return draft;
  }

  return {
    ...draft,
    edges: [
      ...draft.edges,
      {
        id: `edge:${source}:${target}`,
        source,
        target,
        type: 'flow' as const,
      },
    ],
  };
}
