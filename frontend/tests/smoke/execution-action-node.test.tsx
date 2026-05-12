import { describe, expect, it } from 'vitest';
import { defaultFlowNodePosition, isFlowGraphNodeId, toFlowNodeId } from '../../src/features/flows/flowGraphTypes';
import { draftToFlowGraph, flowGraphDocumentToCanvasDraft } from '../../src/features/flows/flowGraphAdapters';

describe('execution action flow nodes', () => {
  it('uses a stable execution_action node id prefix', () => {
    const nodeId = toFlowNodeId('execution_action', 'drive');

    expect(nodeId).toBe('execution_action:drive');
    expect(isFlowGraphNodeId(nodeId)).toBe(true);
    expect(defaultFlowNodePosition('execution_action')).toEqual({ x: 860, y: 500 });
  });

  it('round trips execution action node data through graph adapters', () => {
    const graph = draftToFlowGraph({
      publishedCrews: [],
      draft: {
        selectedNodeId: null,
        nodes: [
          {
            id: 'execution_action:drive',
            type: 'execution_action',
            position: { x: 1, y: 2 },
            data: {
              actionKey: 'ax.google_drive_upload',
              credentialProvider: 'google_workspace',
              credentialId: 'account-1',
              approvalMode: 'every_run',
              configJson: { filename_template: 'image.png' },
              inputBindings: { artifact_id: { source: 'state', path: 'artifact_id' } },
              outputMapping: { url: 'provider_url' },
            },
          },
        ],
        edges: [],
        entities: { crews: {} },
      },
    });

    expect(graph.nodes[0].data).toEqual({
      action_key: 'ax.google_drive_upload',
      credential_provider: 'google_workspace',
      credential_id: 'account-1',
      input_bindings: { artifact_id: { source: 'state', path: 'artifact_id' } },
      config_json: { filename_template: 'image.png' },
      approval_mode: 'every_run',
      idempotency_key_strategy: 'run_node_action_input_hash',
      output_mapping: { url: 'provider_url' },
    });
    expect(graph.nodes[0].data).not.toHaveProperty('actionKey');

    const draft = flowGraphDocumentToCanvasDraft(graph);
    expect(draft.nodes[0].type).toBe('execution_action');
    expect(draft.nodes[0].data).toEqual({
      actionKey: 'ax.google_drive_upload',
      credentialProvider: 'google_workspace',
      credentialId: 'account-1',
      inputBindings: { artifact_id: { source: 'state', path: 'artifact_id' } },
      configJson: { filename_template: 'image.png' },
      approvalMode: 'every_run',
      idempotencyKeyStrategy: 'run_node_action_input_hash',
      outputMapping: { url: 'provider_url' },
    });
  });
});
