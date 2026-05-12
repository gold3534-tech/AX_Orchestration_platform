import { describe, expect, it } from 'vitest';
import {
  addPlaceholderNode,
  bindCanvasNode,
  commitCanvasNodeSize,
  createEmptyCrewCanvasDraft,
  deleteCanvasNode,
  deleteCanvasEdge,
  findStaleCanvasNodeReferences,
  rebindStaleCanvasNodeReferences,
  upsertCanvasEdge,
} from './crewCanvasDraft';
import { getCrewCanvasValidation, getOrderedTaskNodeIds } from './crewCanvasValidation';

describe('crew canvas validation', () => {
  it('orders green chains before unsequenced tasks by insertion order', () => {
    let draft = createEmptyCrewCanvasDraft();
    draft = bindCanvasNode(addPlaceholderNode(draft, { nodeId: 'placeholder:1' }), 'placeholder:1', {
      kind: 'task',
      assetId: 'task-1',
      versionId: 'tv1',
    });
    draft = bindCanvasNode(addPlaceholderNode(draft, { nodeId: 'placeholder:2' }), 'placeholder:2', {
      kind: 'task',
      assetId: 'task-2',
      versionId: 'tv2',
    });
    draft = bindCanvasNode(addPlaceholderNode(draft, { nodeId: 'placeholder:3' }), 'placeholder:3', {
      kind: 'task',
      assetId: 'task-3',
      versionId: 'tv3',
    });
    draft = upsertCanvasEdge(draft, {
      id: 'sequence:3:1',
      kind: 'task_sequence',
      source: 'task:task-3',
      target: 'task:task-1',
    });

    expect(getOrderedTaskNodeIds(draft)).toEqual(['task:task-3', 'task:task-1', 'task:task-2']);
  });

  it('blocks orange context when source task runs after dependent task', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 0 },
        { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'tv2', insertedAt: 1 },
      ],
      edges: [{ id: 'context:2:1', kind: 'task_context', source: 'task:task-2', target: 'task:task-1' }],
      insertionOrder: ['task:task-1', 'task:task-2'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    const validation = getCrewCanvasValidation(draft, { process: 'sequential', action: 'save' });

    expect(validation.isValid).toBe(false);
    expect(validation.errors[0]?.message).toContain('Context source task must run before');
  });

  it('allows sequential draft save without red assignments but blocks validate', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [{ nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 0 }],
      edges: [],
      insertionOrder: ['task:task-1'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    expect(getCrewCanvasValidation(draft, { process: 'sequential', action: 'save' }).isValid).toBe(true);
    expect(getCrewCanvasValidation(draft, { process: 'sequential', action: 'validate' }).isValid).toBe(false);
    expect(getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'publish' }).isValid).toBe(true);
  });

  it('allows empty draft save but blocks validate and publish', () => {
    const draft = createEmptyCrewCanvasDraft();

    expect(getCrewCanvasValidation(draft, { process: 'sequential', action: 'save' }).isValid).toBe(true);
    expect(getCrewCanvasValidation(draft, { process: 'sequential', action: 'validate' }).errors).toEqual([
      {
        code: 'missing_task',
        message: 'Crew canvas must include at least one task before validation or publish.',
      },
    ]);
    expect(getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'publish' }).errors).toEqual([
      {
        code: 'missing_task',
        message: 'Crew canvas must include at least one task before validation or publish.',
      },
    ]);
  });

  it('initializes and commits node sizes in the draft', () => {
    let draft = createEmptyCrewCanvasDraft();

    expect(draft.nodeSizes).toEqual({});

    draft = commitCanvasNodeSize(draft, 'crew:crew-1', { width: 1400, height: 760 });

    expect(draft.nodeSizes).toEqual({
      'crew:crew-1': { width: 1400, height: 760 },
    });
  });

  it('ignores invalid node sizes and removes sizes when deleting a node', () => {
    let draft = createEmptyCrewCanvasDraft();
    draft = commitCanvasNodeSize(draft, 'crew:crew-1', { width: Number.NaN, height: 760 });
    draft = commitCanvasNodeSize(draft, 'placeholder:1', { width: 220, height: 120 });

    expect(draft.nodeSizes).toEqual({
      'placeholder:1': { width: 220, height: 120 },
    });

    draft = deleteCanvasNode(
      {
        ...draft,
        nodes: [{ nodeId: 'placeholder:1', kind: 'placeholder', insertedAt: 0 }],
        insertionOrder: ['placeholder:1'],
      },
      'placeholder:1',
    );

    expect(draft.nodeSizes).toEqual({});
  });

  it('allows placeholder nodes during draft save without requiring a task', () => {
    let draft = addPlaceholderNode(createEmptyCrewCanvasDraft(), { nodeId: 'placeholder:1' });
    expect(getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'save' }).isValid).toBe(true);

    draft = bindCanvasNode(addPlaceholderNode(draft, { nodeId: 'placeholder:2' }), 'placeholder:2', {
      kind: 'task',
      assetId: 'task-1',
      versionId: 'tv1',
    });

    expect(getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'save' }).isValid).toBe(true);

    const publishValidation = getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'publish' });
    expect(publishValidation.isValid).toBe(false);
    expect(publishValidation.errors).toContainEqual({
      code: 'placeholder_unbound',
      message: 'Bind or remove placeholder nodes before validation or publish.',
      nodeId: 'placeholder:1',
    });
  });

  it('blocks multiple red assignments to the same task', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'av1', insertedAt: 0 },
        { nodeId: 'agent:agent-2', kind: 'agent', assetId: 'agent-2', versionId: 'av2', insertedAt: 1 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 2 },
      ],
      edges: [
        { id: 'assignment:1:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' },
        { id: 'assignment:2:1', kind: 'agent_assignment', source: 'agent:agent-2', target: 'task:task-1' },
      ],
      insertionOrder: ['agent:agent-1', 'agent:agent-2', 'task:task-1'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    const validation = getCrewCanvasValidation(draft, { process: 'sequential', action: 'validate' });

    expect(validation.isValid).toBe(false);
    expect(validation.errors.some((error) => error.code === 'agent_assignment_multiple')).toBe(true);
  });

  it('removes related edges when deleting a node', () => {
    const draft = deleteCanvasNode(
      {
        selectedNodeId: 'task:task-1',
        nodes: [
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'av1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 1 },
        ],
        edges: [{ id: 'assignment:1:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' }],
        insertionOrder: ['agent:agent-1', 'task:task-1'],
        nodePositions: { 'task:task-1': { x: 10, y: 20 } },
        nodeSizes: { 'task:task-1': { width: 300, height: 180 } },
      } as const,
      'task:task-1',
    );

    expect(draft.nodes.map((node) => node.nodeId)).toEqual(['agent:agent-1']);
    expect(draft.edges).toEqual([]);
    expect(draft.insertionOrder).toEqual(['agent:agent-1']);
    expect(draft.nodePositions).toEqual({});
    expect(draft.nodeSizes).toEqual({});
    expect(draft.selectedNodeId).toBeNull();
  });

  it('removes a single edge from a draft without deleting connected nodes', () => {
    const draft = deleteCanvasEdge(
      {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'av1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 1 },
        ],
        edges: [
          { id: 'assignment:1:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' },
          { id: 'assignment:stale', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:missing' },
        ],
        insertionOrder: ['agent:agent-1', 'task:task-1'],
        nodePositions: {},
        nodeSizes: {},
      } as const,
      'assignment:1:1',
    );

    expect(draft.nodes.map((node) => node.nodeId)).toEqual(['agent:agent-1', 'task:task-1']);
    expect(draft.edges).toEqual([{ id: 'assignment:stale', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:missing' }]);
  });

  it('preserves edges and position when rebinding the same task id', () => {
    const draft = bindCanvasNode(
      {
        selectedNodeId: 'task:task-1',
        nodes: [
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'av1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 1 },
        ],
        edges: [{ id: 'assignment:1:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' }],
        insertionOrder: ['agent:agent-1', 'task:task-1'],
        nodePositions: { 'task:task-1': { x: 10, y: 20 } },
        nodeSizes: { 'task:task-1': { width: 300, height: 180 } },
      } as const,
      'task:task-1',
      { kind: 'task', assetId: 'task-1', versionId: 'tv2' },
    );

    expect(draft.nodes).toContainEqual({
      nodeId: 'task:task-1',
      kind: 'task',
      assetId: 'task-1',
      versionId: 'tv2',
      insertedAt: 1,
    });
    expect(draft.edges).toEqual([{ id: 'assignment:1:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' }]);
    expect(draft.nodePositions).toEqual({ 'task:task-1': { x: 10, y: 20 } });
    expect(draft.nodeSizes).toEqual({ 'task:task-1': { width: 300, height: 180 } });
    expect(draft.selectedNodeId).toBe('task:task-1');
  });

  it('blocks green cycles and duplicate green input and output', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 0 },
        { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'tv2', insertedAt: 1 },
        { nodeId: 'task:task-3', kind: 'task', assetId: 'task-3', versionId: 'tv3', insertedAt: 2 },
      ],
      edges: [
        { id: 'sequence:1:2', kind: 'task_sequence', source: 'task:task-1', target: 'task:task-2' },
        { id: 'sequence:1:3', kind: 'task_sequence', source: 'task:task-1', target: 'task:task-3' },
        { id: 'sequence:3:2', kind: 'task_sequence', source: 'task:task-3', target: 'task:task-2' },
        { id: 'sequence:2:1', kind: 'task_sequence', source: 'task:task-2', target: 'task:task-1' },
      ],
      insertionOrder: ['task:task-1', 'task:task-2', 'task:task-3'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    const errorCodes = getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'save' }).errors.map((error) => error.code);

    expect(errorCodes).toContain('task_sequence_multiple_output');
    expect(errorCodes).toContain('task_sequence_multiple_input');
    expect(errorCodes).toContain('task_sequence_cycle');
  });

  it('blocks invalid red endpoints and direction', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'av1', insertedAt: 0 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'tv1', insertedAt: 1 },
      ],
      edges: [
        { id: 'assignment:task-to-agent', kind: 'agent_assignment', source: 'task:task-1', target: 'agent:agent-1' },
        { id: 'assignment:agent-to-agent', kind: 'agent_assignment', source: 'agent:agent-1', target: 'agent:agent-1' },
      ],
      insertionOrder: ['agent:agent-1', 'task:task-1'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    const validation = getCrewCanvasValidation(draft, { process: 'hierarchical', action: 'save' });

    expect(validation.isValid).toBe(false);
    expect(validation.errors.map((error) => error.code)).toEqual([
      'agent_assignment_invalid_endpoint',
      'agent_assignment_invalid_endpoint',
    ]);
  });

  it('detects and rebinds stale agent and task node versions without moving canvas state', () => {
    const draft = {
      selectedNodeId: 'task:task-1',
      nodes: [
        { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-old', insertedAt: 0 },
        { nodeId: 'agent:agent-2', kind: 'agent', assetId: 'agent-2', versionId: 'agent-current', insertedAt: 1 },
        { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-old', insertedAt: 2 },
        { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'task-current', insertedAt: 3 },
      ],
      edges: [
        { id: 'assignment:1:1', kind: 'agent_assignment', source: 'agent:agent-1', target: 'task:task-1' },
        { id: 'sequence:1:2', kind: 'task_sequence', source: 'task:task-1', target: 'task:task-2' },
      ],
      insertionOrder: ['agent:agent-1', 'agent:agent-2', 'task:task-1', 'task:task-2'],
      nodePositions: {
        'agent:agent-1': { x: 10, y: 20 },
        'task:task-1': { x: 30, y: 40 },
      },
      nodeSizes: {
        'agent:agent-1': { width: 220, height: 160 },
        'task:task-1': { width: 260, height: 180 },
      },
    } as const;
    const agentAssetsById = new Map([
      ['agent-1', { current_version: { id: 'agent-new' } }],
      ['agent-2', { current_version: { id: 'agent-current' } }],
    ]);
    const taskAssetsById = new Map([
      ['task-1', { current_version: { id: 'task-new' } }],
      ['task-2', { current_version: { id: 'task-current' } }],
    ]);

    expect(findStaleCanvasNodeReferences({ draft, agentAssetsById, taskAssetsById })).toEqual([
      {
        nodeId: 'agent:agent-1',
        kind: 'agent',
        assetId: 'agent-1',
        currentVersionId: 'agent-old',
        latestVersionId: 'agent-new',
      },
      {
        nodeId: 'task:task-1',
        kind: 'task',
        assetId: 'task-1',
        currentVersionId: 'task-old',
        latestVersionId: 'task-new',
      },
    ]);

    const rebound = rebindStaleCanvasNodeReferences({ draft, agentAssetsById, taskAssetsById });

    expect(rebound.nodes).toEqual([
      { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-new', insertedAt: 0 },
      { nodeId: 'agent:agent-2', kind: 'agent', assetId: 'agent-2', versionId: 'agent-current', insertedAt: 1 },
      { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-new', insertedAt: 2 },
      { nodeId: 'task:task-2', kind: 'task', assetId: 'task-2', versionId: 'task-current', insertedAt: 3 },
    ]);
    expect(rebound.edges).toBe(draft.edges);
    expect(rebound.insertionOrder).toBe(draft.insertionOrder);
    expect(rebound.nodePositions).toBe(draft.nodePositions);
    expect(rebound.nodeSizes).toBe(draft.nodeSizes);
    expect(rebound.selectedNodeId).toBe('task:task-1');
  });

  it('ignores missing assets during stale version detection', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [
        { nodeId: 'agent:missing-agent', kind: 'agent', assetId: 'missing-agent', versionId: 'agent-old', insertedAt: 0 },
        { nodeId: 'task:missing-task', kind: 'task', assetId: 'missing-task', versionId: 'task-old', insertedAt: 1 },
      ],
      edges: [],
      insertionOrder: ['agent:missing-agent', 'task:missing-task'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    expect(
      findStaleCanvasNodeReferences({
        draft,
        agentAssetsById: new Map(),
        taskAssetsById: new Map(),
      }),
    ).toEqual([]);
    expect(
      rebindStaleCanvasNodeReferences({
        draft,
        agentAssetsById: new Map(),
        taskAssetsById: new Map(),
      }),
    ).toEqual(draft);
  });

  it('normalizes whitespace around latest version ids during stale version detection', () => {
    const draft = {
      selectedNodeId: null,
      nodes: [{ nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-current', insertedAt: 0 }],
      edges: [],
      insertionOrder: ['agent:agent-1'],
      nodePositions: {},
      nodeSizes: {},
    } as const;

    expect(
      findStaleCanvasNodeReferences({
        draft,
        agentAssetsById: new Map([['agent-1', { current_version: { id: '  agent-current  ' } }]]),
        taskAssetsById: new Map(),
      }),
    ).toEqual([]);
    expect(
      rebindStaleCanvasNodeReferences({
        draft,
        agentAssetsById: new Map([['agent-1', { current_version: { id: '  agent-current  ' } }]]),
        taskAssetsById: new Map(),
      }),
    ).toBe(draft);
  });
});
