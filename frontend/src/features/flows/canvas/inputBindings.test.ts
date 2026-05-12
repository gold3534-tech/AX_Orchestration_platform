import { describe, expect, it } from 'vitest';
import type { FlowCanvasDraft, PublishedCrewOption } from '../hooks';
import {
  buildTransformInputMapping,
  findUnresolvedFlowInputs,
  formatUnresolvedFlowInputs,
  missingInputsByNodeId,
} from './inputBindings';

const visualCrew: PublishedCrewOption = {
  assetId: 'crew-asset-1',
  versionId: 'crew-version-1',
  versionNo: 1,
  name: 'Visual Crew',
  description: '',
  status: 'published',
  runtimeSnapshot: {
    required_inputs: ['topic', 'card_news_slides'],
  },
};

function createDraft(nodes: FlowCanvasDraft['nodes']): FlowCanvasDraft {
  return {
    selectedNodeId: null,
    nodes,
    edges: [],
  };
}

describe('input binding helpers', () => {
  it('finds Visual Crew.card_news_slides unresolved', () => {
    const draft = createDraft([
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 0, y: 0 },
        data: {
          versionId: visualCrew.versionId,
          inputMappings: {
            topic: { source: 'state', path: 'topic' },
          },
        },
      },
    ]);

    expect(findUnresolvedFlowInputs(draft, [visualCrew])).toEqual([
      {
        nodeId: 'crew:visual',
        crewName: 'Visual Crew',
        inputName: 'card_news_slides',
      },
    ]);
  });

  it('treats topic as satisfied when input node declares topic', () => {
    const draft = createDraft([
      {
        id: 'input:main',
        type: 'input',
        position: { x: 0, y: 0 },
        data: {
          fields: [{ name: 'topic', type: 'string', required: true }],
        },
      },
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 0, y: 0 },
        data: {
          versionId: visualCrew.versionId,
          inputMappings: {
            card_news_slides: { source: 'state', path: 'card_news_slides' },
          },
        },
      },
    ]);

    expect(findUnresolvedFlowInputs(draft, [visualCrew])).toEqual([]);
  });

  it('builds transform mapping with default maxChars 8000 and overflow fail', () => {
    expect(
      buildTransformInputMapping({
        sourceNodeId: 'crew:research',
        paths: ['crew:research.json.slides'],
        inputType: 'structured',
        transform: 'join_card_news_slides_v1',
      }),
    ).toEqual({
      source: 'transform',
      nodeId: 'crew:research',
      paths: ['crew:research.json.slides'],
      inputType: 'structured',
      transform: 'join_card_news_slides_v1',
      maxChars: 8000,
      overflow: 'fail',
    });
  });

  it('groups missing inputs by node id from draft and published crews', () => {
    const draft = createDraft([
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 0, y: 0 },
        data: {
          versionId: visualCrew.versionId,
          inputMappings: {
            topic: { source: 'state', path: 'topic' },
          },
        },
      },
    ]);

    expect(missingInputsByNodeId(draft, [visualCrew])).toEqual({
      'crew:visual': ['card_news_slides'],
    });
  });

  it('formats unresolved inputs as Visual Crew.card_news_slides', () => {
    expect(
      formatUnresolvedFlowInputs([
        {
          nodeId: 'crew:visual',
          crewName: 'Visual Crew',
          inputName: 'card_news_slides',
        },
      ]),
    ).toBe('Visual Crew.card_news_slides');
  });
});
