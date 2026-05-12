import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { CrewBuilderCanvas, getCrewCanvasConnectionKind, isCrewCanvasConnectionValid } from '../../src/features/crews/CrewBuilderCanvas';
import { crewGraphDocumentToCanvasDraft, draftToCrewGraph } from '../../src/features/crews/crewGraphAdapters';
import { buildCrewGraphDocument } from '../../src/features/crews/hooks';
import {
  AGENT_ASSIGNMENT_SOURCE_HANDLE,
  AGENT_ASSIGNMENT_TARGET_HANDLE,
  TASK_CONTEXT_SOURCE_HANDLE,
  TASK_CONTEXT_TARGET_HANDLE,
  TASK_SEQUENCE_SOURCE_HANDLE,
  TASK_SEQUENCE_TARGET_HANDLE,
} from '../../src/features/crews/canvas/CrewCanvasNodes';

vi.mock('@xyflow/react', async () => {
  const React = await import('react');

  return {
    Background: () => null,
    BackgroundVariant: { Lines: 'lines' },
    Controls: () => null,
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
    Handle: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    ReactFlow: ({ children, edges = [], isValidConnection, onEdgesChange }: any) => (
      <div data-testid="mock-react-flow">
        {children}
        {isValidConnection ? <span data-testid="strict-connection-validation" /> : null}
        {edges.map((edge: any) => (
          <button
            key={edge.id}
            type="button"
            onClick={() => onEdgesChange?.([{ type: 'remove', id: edge.id }])}
          >
            Remove edge {edge.id}
          </button>
        ))}
      </div>
    ),
    applyEdgeChanges: (changes: any[], edges: any[]) =>
      edges.filter((edge) => !changes.some((change) => change.type === 'remove' && change.id === edge.id)),
    applyNodeChanges: (_changes: any[], nodes: any[]) => nodes,
  };
});

test('maps only matching strict input and output handles to crew edge kinds', () => {
  const redConnection = {
    source: 'agent:agent-1',
    target: 'task:task-1',
    sourceHandle: AGENT_ASSIGNMENT_SOURCE_HANDLE,
    targetHandle: AGENT_ASSIGNMENT_TARGET_HANDLE,
  };
  expect(getCrewCanvasConnectionKind(redConnection)).toBe('agent_assignment');
  expect(isCrewCanvasConnectionValid(redConnection)).toBe(true);
  expect(
    getCrewCanvasConnectionKind({
      sourceHandle: TASK_CONTEXT_SOURCE_HANDLE,
      targetHandle: TASK_CONTEXT_TARGET_HANDLE,
    }),
  ).toBe('task_context');
  expect(
    getCrewCanvasConnectionKind({
      sourceHandle: TASK_SEQUENCE_SOURCE_HANDLE,
      targetHandle: TASK_SEQUENCE_TARGET_HANDLE,
    }),
  ).toBe('task_sequence');
  expect(
    getCrewCanvasConnectionKind({
      sourceHandle: TASK_CONTEXT_SOURCE_HANDLE,
      targetHandle: TASK_SEQUENCE_TARGET_HANDLE,
    }),
  ).toBeNull();
  expect(
    getCrewCanvasConnectionKind({
      sourceHandle: TASK_SEQUENCE_SOURCE_HANDLE,
      targetHandle: AGENT_ASSIGNMENT_TARGET_HANDLE,
    }),
  ).toBeNull();
  expect(
    isCrewCanvasConnectionValid({
      source: 'agent:agent-1',
      target: 'task:task-1',
      sourceHandle: AGENT_ASSIGNMENT_SOURCE_HANDLE,
      targetHandle: TASK_CONTEXT_TARGET_HANDLE,
    }),
  ).toBe(false);
});

test('adds a placeholder node from the canvas toolbar and renders legend', () => {
  const onAddNode = vi.fn();
  render(
    <CrewBuilderCanvas
      graph={{ nodes: [], edges: [] }}
      selectedNodeId={null}
      onSelectNode={() => undefined}
      onAddFirstNode={() => undefined}
      onAddNode={onAddNode}
    />,
  );

  expect(screen.getAllByText('Add Node').length).toBeGreaterThan(0);
  expect(screen.getByText('🔴: Assign a agent')).toBeInTheDocument();
  expect(screen.getByText('🟠: Context Transfer')).toBeInTheDocument();
  expect(screen.getByText('🟢: Task Sequence')).toBeInTheDocument();
  expect(screen.getByTestId('strict-connection-validation')).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('button', { name: /add node/i })[0]);
  expect(onAddNode).toHaveBeenCalledTimes(1);
});

test('crew task list editor is not rendered', () => {
  render(
    <CrewBuilderCanvas
      graph={{ nodes: [], edges: [] }}
      selectedNodeId={null}
      onSelectNode={() => undefined}
      onAddFirstNode={() => undefined}
    />,
  );

  expect(screen.queryByText('Task rows')).not.toBeInTheDocument();
  expect(screen.queryByText('Add Task Row')).not.toBeInTheDocument();
});

test('removes a runtime edge from the canvas draft path', () => {
  const onDeleteEdge = vi.fn();

  render(
    <CrewBuilderCanvas
      graph={{
        nodes: [],
        edges: [{ id: 'assign:1', source: 'agent:agent-1', target: 'task:task-1', type: 'agent_assignment' } as any],
      }}
      selectedNodeId={null}
      onSelectNode={() => undefined}
      onAddFirstNode={() => undefined}
      onDeleteEdge={onDeleteEdge}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: /remove edge assign:1/i }));

  expect(onDeleteEdge).toHaveBeenCalledWith('assign:1');
});

test('serializes direct canvas nodes and colored runtime edges', () => {
  const crewAsset = {
    id: 'crew-1',
    name: 'Crew Alpha',
    description: 'Crew',
    current_version: { id: 'crew-v1', version_no: 1, status: 'draft', payload: { process: 'sequential' } },
  } as any;
  const agentAsset = {
    id: 'agent-1',
    name: 'Agent Alpha',
    description: 'Agent',
    current_version: { id: 'agent-v1', version_no: 1, status: 'draft', payload: { role: 'Researcher' } },
  } as any;
  const taskOne = {
    id: 'task-1',
    name: 'Task One',
    description: 'Task',
    current_version: {
      id: 'task-v1',
      version_no: 1,
      status: 'draft',
      payload: { description: 'One', expected_output: 'One out' },
    },
  } as any;
  const taskTwo = {
    id: 'task-2',
    name: 'Task Two',
    description: 'Task',
    current_version: {
      id: 'task-v2',
      version_no: 1,
      status: 'draft',
      payload: { description: 'Two', expected_output: 'Two out' },
    },
  } as any;

  const graph = buildCrewGraphDocument({
    crewAsset,
    draft: {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'placeholder:drop-1', kind: 'placeholder', insertedAt: 0 },
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 1 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 2 },
        { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'task-v2', insertedAt: 3 },
      ],
      edges: [
        { id: 'assign:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' },
        { id: 'context:1:2', kind: 'task_context', source: 'task:task-1', target: 'task:task-2' },
        { id: 'sequence:1:2', kind: 'task_sequence', source: 'task:task-1', target: 'task:task-2' },
      ],
      insertionOrder: ['placeholder:drop-1', 'agent:agent-1', 'task:task-1', 'task:task-2'],
      nodePositions: {
        'placeholder:drop-1': { x: 12, y: 24 },
        'task:task-2': { x: 420, y: 260 },
      },
    },
    agentAssetsById: new Map([['agent-1', agentAsset]]),
    taskAssetsById: new Map([
      ['task-1', taskOne],
      ['task-2', taskTwo],
    ]),
    toolCatalogByKey: new Map(),
  });

  expect(graph.nodes.map((node) => node.type)).toEqual(['crew', 'placeholder', 'agent', 'task', 'task']);
  expect(graph.nodes.find((node) => node.id === 'placeholder:drop-1')?.position).toEqual({ x: 12, y: 24 });
  expect(graph.nodes.find((node) => node.id === 'task:task-2')?.position).toEqual({ x: 420, y: 260 });
  expect(graph.edges).toEqual([
    expect.objectContaining({ id: 'assign:1', source: 'agent:agent-1', target: 'task:task-1', type: 'agent_assignment' }),
    expect.objectContaining({ id: 'context:1:2', source: 'task:task-1', target: 'task:task-2', type: 'task_context' }),
    expect.objectContaining({ id: 'sequence:1:2', source: 'task:task-1', target: 'task:task-2', type: 'task_sequence' }),
  ]);
  expect(graph.nodes.find((node) => node.id === 'agent:agent-1')?.data).toEqual({
    assetId: 'agent-1',
    versionId: 'agent-v1',
  });
});

test('loads direct graph assignment, sequence, and task positions into the current draft shape', () => {
  const draft = crewGraphDocumentToCanvasDraft({
    schemaVersion: 1,
    nodes: [
      { id: 'crew:crew-1', type: 'crew', position: { x: 0, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
      { id: 'agent:agent-1', type: 'agent', position: { x: 100, y: 100 }, data: { assetId: 'agent-1', versionId: 'agent-v1' } },
      { id: 'task:task-2', type: 'task', position: { x: 540, y: 100 }, data: { assetId: 'task-2', versionId: 'task-v2' } },
      { id: 'task:task-3', type: 'task', position: { x: 760, y: 100 }, data: { assetId: 'task-3', versionId: 'task-v3' } },
      { id: 'task:task-1', type: 'task', position: { x: 300, y: 100 }, data: { assetId: 'task-1', versionId: 'task-v1' } },
    ],
    edges: [
      { id: 'assign:1', source: 'agent:agent-1', target: 'task:task-1', type: 'agent_assignment' },
      { id: 'sequence:1:2', source: 'task:task-1', target: 'task:task-2', type: 'task_sequence' },
      { id: 'context:1:2', source: 'task:task-1', target: 'task:task-2', type: 'task_context' },
    ],
    entities: {},
  });

  expect(draft.nodes).toEqual([
    { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 1 },
    { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'task-v2', insertedAt: 2 },
    { nodeId: 'task:task-3', kind: 'task', assetId: 'task-3', versionId: 'task-v3', insertedAt: 3 },
    { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 4 },
  ]);
  expect(draft.edges).toEqual([
    { id: 'assign:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' },
    { id: 'sequence:1:2', kind: 'task_sequence', source: 'task:task-1', target: 'task:task-2' },
    { id: 'context:1:2', kind: 'task_context', source: 'task:task-1', target: 'task:task-2' },
  ]);
  expect(draft.nodePositions['task:task-1']).toEqual({ x: 300, y: 100 });
  expect(draft.nodePositions['task:task-2']).toEqual({ x: 540, y: 100 });
  expect(draft.nodePositions['task:task-3']).toEqual({ x: 760, y: 100 });

  const visibleGraph = draftToCrewGraph({
    draft,
    crew: { assetId: 'crew-1', name: 'Crew Alpha', description: 'Crew' },
    availableAgents: [{ assetId: 'agent-1', versionId: 'agent-v1', name: 'Agent Alpha', subtitle: 'Agent', toolKeys: [] }],
    availableTasks: [
      { assetId: 'task-1', versionId: 'task-v1', name: 'Task One', subtitle: 'Task', toolKeys: [] },
      { assetId: 'task-2', versionId: 'task-v2', name: 'Task Two', subtitle: 'Task', toolKeys: [] },
      { assetId: 'task-3', versionId: 'task-v3', name: 'Task Three', subtitle: 'Task', toolKeys: [] },
    ],
    availableTools: [],
  });
  expect(visibleGraph.edges).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        source: 'agent:agent-1',
        sourceHandle: AGENT_ASSIGNMENT_SOURCE_HANDLE,
        target: 'task:task-1',
        targetHandle: AGENT_ASSIGNMENT_TARGET_HANDLE,
        data: { kind: 'agent_assignment' },
      }),
      expect.objectContaining({
        source: 'task:task-1',
        sourceHandle: TASK_SEQUENCE_SOURCE_HANDLE,
        target: 'task:task-2',
        targetHandle: TASK_SEQUENCE_TARGET_HANDLE,
        data: { kind: 'task_sequence' },
      }),
      expect.objectContaining({
        source: 'task:task-1',
        sourceHandle: TASK_CONTEXT_SOURCE_HANDLE,
        target: 'task:task-2',
        targetHandle: TASK_CONTEXT_TARGET_HANDLE,
        data: { kind: 'task_context' },
      }),
    ]),
  );
});

test('serializes direct canvas tool attachment entities without tool nodes or edges', () => {
  const crewAsset = {
    id: 'crew-1',
    name: 'Crew Alpha',
    description: 'Crew',
    current_version: { id: 'crew-v1', version_no: 1, status: 'draft', payload: { process: 'sequential' } },
  } as any;
  const agentAsset = {
    id: 'agent-1',
    name: 'Agent Alpha',
    description: 'Agent',
    current_version: { id: 'agent-v1', version_no: 1, status: 'draft', payload: { role: 'Researcher' } },
  } as any;
  const taskAsset = {
    id: 'task-1',
    name: 'Task One',
    description: 'Task',
    current_version: {
      id: 'task-v1',
      version_no: 1,
      status: 'draft',
      payload: { description: 'One', expected_output: 'One out' },
    },
  } as any;
  const searchTool = {
    tool_key: 'crewai.serper_dev',
    name: 'Serper Dev Search',
    description: 'Search the web',
    tool_type: 'local',
    module_path: 'crewai_tools',
    class_name: 'SerperDevTool',
    default_config_json: { country: 'us' },
  } as any;
  const imageTool = {
    tool_key: 'crewai.dalle',
    name: 'DALL-E Tool',
    description: 'Generate images',
    tool_type: 'local',
    module_path: 'crewai_tools',
    class_name: 'DallETool',
    default_config_json: {},
  } as any;

  const graph = buildCrewGraphDocument({
    crewAsset,
    draft: {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 0 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
      ],
      edges: [{ id: 'assign:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' }],
      insertionOrder: ['agent:agent-1', 'task:task-1'],
      nodePositions: {},
    },
    agentAssetsById: new Map([['agent-1', agentAsset]]),
    taskAssetsById: new Map([['task-1', taskAsset]]),
    toolCatalogByKey: new Map([
      ['crewai.serper_dev', searchTool],
      ['crewai.dalle', imageTool],
    ]),
    agentVersionTools: new Map([['agent-v1', ['crewai.serper_dev']]]),
    taskVersionTools: new Map([['task-v1', ['crewai.dalle']]]),
  });

  expect(graph.nodes.map((node) => node.id)).toEqual([
    'crew:crew-1',
    'agent:agent-1',
    'task:task-1',
  ]);
  expect(graph.edges.map((edge) => edge.type)).toEqual(['agent_assignment']);
  expect(graph.entities.tools['crewai.serper_dev']).toMatchObject({
    tool_key: 'crewai.serper_dev',
    name: 'Serper Dev Search',
    attachments: [{ version_id: 'agent-v1', sort_order: 0 }],
  });
  expect(graph.entities.tools['crewai.dalle']).toMatchObject({
    tool_key: 'crewai.dalle',
    name: 'DALL-E Tool',
    attachments: [{ version_id: 'task-v1', sort_order: 0 }],
  });
});
