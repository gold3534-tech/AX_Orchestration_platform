import { describe, expect, test } from 'vitest';
import { crewGraphDocumentToCanvasDraft, draftToCrewGraph } from '../crewGraphAdapters';
import { canvasDraftToGraphDocument } from './crewCanvasGraph';

function asset(assetType: string, id: string, versionId: string, payload: Record<string, unknown> = {}) {
  return {
    id,
    asset_type: assetType,
    name: id,
    description: '',
    current_version: {
      id: versionId,
      version_no: 1,
      status: 'published',
      payload,
      metadata_json: {},
    },
  } as never;
}

describe('canvasDraftToGraphDocument', () => {
  test('preserves saved tool_config_json in graph tool attachments', () => {
    const crewAsset = asset('crew', 'crew-1', 'crew-v1', { process: 'sequential' });
    const agentAsset = asset('agent', 'agent-1', 'agent-v1', { role: 'Image Director' });
    const taskAsset = asset('task', 'task-1', 'task-v1', { description: 'Generate image' });
    const configSchema = {
      type: 'object',
      properties: {
        aspect_ratio: {
          type: 'string',
          enum: ['1:1', '9:16'],
        },
      },
    };
    const inputSchema = {
      type: 'object',
      properties: {
        prompt: { type: 'string' },
      },
    };
    const uiSchema = {
      aspect_ratio: {
        'ui:widget': 'select',
      },
    };
    const requiredEnvVars = [{ name: 'GOOGLE_API_KEY' }];
    const credentialRequirements = [
      {
        provider: 'google',
        env_var: 'GOOGLE_API_KEY',
        required: true,
        injection: 'env',
      },
    ];
    const graph = canvasDraftToGraphDocument({
      crewAsset,
      draft: {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
        ],
        edges: [{ id: 'edge:agent-task', source: 'agent:agent-1', target: 'task:task-1', kind: 'agent_assignment' }],
        insertionOrder: ['agent:agent-1', 'task:task-1'],
        nodePositions: {},
        nodeSizes: {},
      },
      agentAssetsById: new Map([['agent-1', agentAsset]]),
      taskAssetsById: new Map([['task-1', taskAsset]]),
      toolCatalogByKey: new Map([
        [
          'ax.nano_banana_image',
          {
            tool_key: 'ax.nano_banana_image',
            name: 'AX Nano Banana Image',
            description: 'Generate image artifacts.',
            tool_type: 'python_class',
            module_path: 'api.tools.nano_banana_image_tool',
            class_name: 'AXNanoBananaImageTool',
            default_config_json: {},
            config_schema_json: configSchema,
            input_schema_json: inputSchema,
            ui_schema_json: uiSchema,
            required_env_vars: requiredEnvVars,
            credential_requirements: credentialRequirements,
          } as never,
        ],
      ]),
      agentVersionTools: new Map([['agent-v1', ['ax.nano_banana_image']]]),
      taskVersionTools: new Map(),
      agentVersionToolAttachments: new Map([
        [
          'agent-v1',
          [
            {
              tool_key: 'ax.nano_banana_image',
              tool_config_json: { model: 'gemini-3-pro-image-preview', aspect_ratio: '9:16', image_size: '2K' },
              sort_order: 7,
            },
          ],
        ],
      ]),
      taskVersionToolAttachments: new Map(),
    });

    const tool = graph.entities.tools['ax.nano_banana_image'];
    expect(tool).toMatchObject({
      config_schema_json: configSchema,
      input_schema_json: inputSchema,
      ui_schema_json: uiSchema,
      required_env_vars: requiredEnvVars,
      credential_requirements: credentialRequirements,
    });
    expect(tool.attachments).toEqual([
      {
        version_id: 'agent-v1',
        tool_config_json: { model: 'gemini-3-pro-image-preview', aspect_ratio: '9:16', image_size: '2K' },
        sort_order: 7,
      },
    ]);
  });

  test('projects selected agent knowledge attachments into graph entities', () => {
    const crewAsset = asset('crew', 'crew-1', 'crew-v1', { process: 'sequential' });
    const agentAsset = asset('agent', 'agent-1', 'agent-v1', { role: 'RFP Analyst' });
    const taskAsset = asset('task', 'task-1', 'task-v1', { description: 'Analyze RFP' });

    const graph = canvasDraftToGraphDocument({
      crewAsset,
      draft: {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 0 },
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 1 },
        ],
        edges: [{ id: 'edge:agent-task', source: 'agent:agent-1', target: 'task:task-1', kind: 'agent_assignment' }],
        insertionOrder: ['agent:agent-1', 'task:task-1'],
        nodePositions: {},
        nodeSizes: {},
      },
      agentAssetsById: new Map([['agent-1', agentAsset]]),
      taskAssetsById: new Map([['task-1', taskAsset]]),
      toolCatalogByKey: new Map(),
      agentVersionKnowledgeAttachments: new Map([
        [
          'agent-v1',
          [
            {
              knowledge_item_id: 'knowledge-1',
              knowledge: {
                id: 'knowledge-1',
                name: '제안요청서',
                status: 'ready',
                source_file_name: 'rfp.pdf',
              },
              sort_order: 0,
            },
          ],
        ],
      ]),
    });

    expect(graph.entities.knowledge).toEqual({
      'knowledge-1': {
        id: 'knowledge-1',
        name: '제안요청서',
        status: 'ready',
        attachments: [{ version_id: 'agent-v1', sort_order: 0 }],
      },
    });
  });

  test('writes saved crew container dimensions to the graph document', () => {
    const crewAsset = asset('crew', 'crew-1', 'crew-v1', { process: 'sequential' });

    const graph = canvasDraftToGraphDocument({
      crewAsset,
      draft: {
        selectedNodeId: null,
        nodes: [],
        edges: [],
        insertionOrder: [],
        nodePositions: {},
        nodeSizes: { 'crew:crew-1': { width: 1440, height: 820 } },
      },
      agentAssetsById: new Map(),
      taskAssetsById: new Map(),
      toolCatalogByKey: new Map(),
    });

    expect(graph.nodes[0]).toMatchObject({
      id: 'crew:crew-1',
      type: 'crew',
      style: { width: 1440, height: 820 },
    });
  });

  test('reads saved crew container dimensions from the graph document', () => {
    const draft = crewGraphDocumentToCanvasDraft({
      schemaVersion: 1,
      layoutDirection: null,
      viewport: null,
      nodes: [
        {
          id: 'crew:crew-1',
          type: 'crew',
          position: { x: 32, y: 32 },
          style: { width: 1440, height: 820 },
          data: { assetId: 'crew-1', versionId: 'crew-v1' },
        },
      ],
      edges: [],
    });

    expect(draft.nodeSizes).toEqual({
      'crew:crew-1': { width: 1440, height: 820 },
    });
  });

  test('ignores invalid saved crew container dimensions while loading a graph document', () => {
    const draft = crewGraphDocumentToCanvasDraft({
      schemaVersion: 1,
      layoutDirection: null,
      viewport: null,
      nodes: [
        {
          id: 'crew:crew-1',
          type: 'crew',
          position: { x: 32, y: 32 },
          style: { width: -1, height: 820 },
          data: { assetId: 'crew-1', versionId: 'crew-v1' },
        },
      ],
      edges: [],
    });

    expect(draft.nodeSizes).toEqual({});
  });

  test('uses saved crew container dimensions in the visible crew graph', () => {
    const draft = crewGraphDocumentToCanvasDraft({
      schemaVersion: 1,
      layoutDirection: null,
      viewport: null,
      nodes: [
        {
          id: 'crew:crew-1',
          type: 'crew',
          position: { x: 32, y: 32 },
          style: { width: 1440, height: 820 },
          data: { assetId: 'crew-1', versionId: 'crew-v1' },
        },
      ],
      edges: [],
    });

    const graph = draftToCrewGraph({
      draft,
      crew: { assetId: 'crew-1', name: 'Crew 1', description: 'Saved crew' },
      availableAgents: [],
      availableTasks: [],
      availableTools: [],
    });

    expect(graph.nodes[0]).toMatchObject({
      id: 'crew:crew-1',
      type: 'crew',
      style: { width: 1440, height: 820 },
    });
  });

  test('auto-expands crew container to include child node bounds', () => {
    const graph = draftToCrewGraph({
      draft: {
        selectedNodeId: null,
        nodes: [
          { nodeId: 'task:task-1', kind: 'task', assetId: 'task-1', versionId: 'task-v1', insertedAt: 0 },
          { nodeId: 'agent:agent-1', kind: 'agent', assetId: 'agent-1', versionId: 'agent-v1', insertedAt: 1 },
        ],
        edges: [],
        insertionOrder: ['task:task-1', 'agent:agent-1'],
        nodePositions: {
          'task:task-1': { x: 1280, y: 120 },
          'agent:agent-1': { x: 96, y: 760 },
        },
        nodeSizes: { 'crew:crew-1': { width: 900, height: 400 } },
      },
      crew: { assetId: 'crew-1', name: 'Crew 1', description: '', status: 'draft' },
      availableAgents: [{ assetId: 'agent-1', versionId: 'agent-v1', name: 'Agent 1', subtitle: '', toolKeys: [] }],
      availableTasks: [{ assetId: 'task-1', versionId: 'task-v1', name: 'Task 1', subtitle: '', toolKeys: [] }],
      availableTools: [],
    });

    expect(graph.nodes[0]?.style).toMatchObject({ width: 1580, height: 1040 });
  });
});
