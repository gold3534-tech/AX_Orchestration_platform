import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { createEmptyFlowCanvasDraft } from '../../src/features/flows/hooks';
import type { FlowCanvasDraft } from '../../src/features/flows/hooks';
import { draftToFlowGraph, flowGraphDocumentToCanvasDraft } from '../../src/features/flows/flowGraphAdapters';
import {
  FLOW_EDGE_STYLE,
  FlowBuilderCanvas,
  connectFlowCanvasNodes,
  getCrewFlowNodeDimensions,
  getCrewStepSummaries,
} from '../../src/features/flows/FlowBuilderCanvas';
import type { FlowNodeKind } from '../../src/features/flows/flowGraphTypes';

const publishedCrew = {
  assetId: 'crew-1',
  versionId: 'crew-v1',
  versionNo: 1,
  name: 'Research Crew',
  description: 'Research',
  status: 'published',
  runtimeSnapshot: {
    schemaVersion: 1,
    runtime_crew: { task_version_ids: ['task-v1'] },
    runtime_agents: {
      'agent-v1': { agent_name: 'Research Agent' },
    },
    runtime_tasks: {
      'task-v1': { task_name: 'Research Task' },
    },
    task_agent_links: {
      'task-v1': 'agent-v1',
    },
    task_tool_links: {
      'task-v1': ['web_search'],
    },
    runtime_tools: {
      web_search: { name: 'Web Search' },
    },
  },
};

const publishedCrewWithAgentAndTaskTools = {
  ...publishedCrew,
  runtimeSnapshot: {
    ...publishedCrew.runtimeSnapshot,
    agent_tool_links: {
      'agent-v1': ['directory_read'],
    },
    task_tool_links: {
      'task-v1': ['web_search'],
    },
    runtime_tools: {
      directory_read: { name: 'Directory Read' },
      web_search: { name: 'Web Search' },
    },
  },
};

const contentCrew = {
  ...publishedCrew,
  assetId: 'crew-content',
  versionId: 'crew-content-v1',
  name: 'Content Crew',
  runtimeSnapshot: {
    ...publishedCrew.runtimeSnapshot,
    output_schema: {
      type: 'object',
      properties: {
        title_slide: { type: 'string' },
        body_slides: { type: 'array' },
        outro_slide: { type: 'string' },
      },
    },
  },
};

const visualCrew = {
  ...publishedCrew,
  assetId: 'crew-visual',
  versionId: 'crew-visual-v1',
  name: 'Visual Crew',
  runtimeSnapshot: {
    ...publishedCrew.runtimeSnapshot,
    required_inputs: ['card_news_slides'],
  },
};

const backupContentCrew = {
  ...contentCrew,
  assetId: 'crew-backup-content',
  versionId: 'crew-backup-content-v1',
  name: 'Backup Content Crew',
};

const unrelatedCrew = {
  ...contentCrew,
  assetId: 'crew-unrelated',
  versionId: 'crew-unrelated-v1',
  name: 'Unrelated Crew',
};

test('builds a flow graph document from a minimal canvas draft', () => {
  const draft: FlowCanvasDraft = {
    ...createEmptyFlowCanvasDraft(),
    nodes: [
      {
        id: 'input:main',
        type: 'input',
        position: { x: 64, y: 160 },
        data: { fields: [{ name: 'topic', type: 'string', required: true }] },
      },
      { id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: { triggerType: 'manual' } },
      {
        id: 'crew:research',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: {
          assetId: 'crew-1',
          versionId: 'crew-v1',
          inputMappings: { topic: { source: 'state', path: 'topic' } },
        },
      },
      {
        id: 'output:main',
        type: 'output',
        position: { x: 900, y: 160 },
        data: { fields: [{ label: 'Answer', source: 'node', nodeId: 'crew:research', path: 'output.final_answer' }] },
      },
    ],
    edges: [
      { id: 'edge:input:start', source: 'input:main', target: 'start:main', type: 'flow' },
      { id: 'edge:start:crew', source: 'start:main', target: 'crew:research', type: 'flow' },
      { id: 'edge:crew:output', source: 'crew:research', target: 'output:main', type: 'flow' },
    ],
  };

  const graph = draftToFlowGraph({
    draft,
    publishedCrews: [
      {
        assetId: 'crew-1',
        versionId: 'crew-v1',
        versionNo: 1,
        name: 'Research Crew',
        description: 'Research workflow crew',
        status: 'published',
        runtimeSnapshot: {
          schemaVersion: 1,
          required_inputs: ['topic'],
          output_schema: { type: 'object', properties: { final_answer: { type: 'string' } } },
        },
      },
    ],
  });

  expect(graph.nodes.map((node) => node.type)).toEqual(['input', 'start', 'crew', 'output']);
  expect(graph.entities?.crews?.['crew-v1']?.runtime_snapshot_json).toEqual(
    expect.objectContaining({ schemaVersion: 1 }),
  );
});

test('loads a saved flow graph document into an editable draft', () => {
  const draft = flowGraphDocumentToCanvasDraft({
    schemaVersion: 1,
    nodes: [{ id: 'start:main', type: 'start', position: { x: 12, y: 24 }, data: { triggerType: 'manual' } }],
    edges: [],
  });

  expect(draft.nodes[0]).toEqual({
    id: 'start:main',
    type: 'start',
    position: { x: 12, y: 24 },
    data: { triggerType: 'manual' },
  });
});

test('renders flow draft nodes as canvas cards', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [{ id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: { triggerType: 'manual' } }],
    edges: [],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  expect(screen.getAllByText('Start').length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText('Manual trigger')).toBeInTheDocument();
});

test('uses one simple brand card style for non-crew flow nodes', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      { id: 'input:main', type: 'input', position: { x: 40, y: 160 }, data: { fields: [] } },
      { id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: { triggerType: 'manual' } },
      { id: 'router:main', type: 'router', position: { x: 640, y: 160 }, data: {} },
      { id: 'hitl:main', type: 'hitl', position: { x: 960, y: 160 }, data: {} },
      { id: 'execution_action:main', type: 'execution_action', position: { x: 1280, y: 160 }, data: {} },
      {
        id: 'output:main',
        type: 'output' as const,
        position: { x: 1600, y: 160 },
        data: { fields: [{ label: 'Answer', source: 'node', nodeId: 'crew:research', path: 'output.final_answer' }] },
      },
    ],
    edges: [],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  ['input:main', 'start:main', 'router:main', 'hitl:main', 'execution_action:main', 'output:main'].forEach((nodeId) => {
    const node = screen.getByTestId(`rf__node-${nodeId}`);

    expect(node).toHaveStyle({ width: '250px', height: '116px' });
    expect(node.firstElementChild).toHaveClass(
      'border-2',
      'border-cyan-300',
      'bg-white',
      'text-stone-950',
      'text-left',
      'shadow-[0_16px_36px_rgba(45,38,70,0.14)]',
    );
    expect(node.querySelector('.react-flow__handle-right')).toHaveClass('!bg-cyan-400');
  });
});

test('uses brand styling for flow edges and crew output handles', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      { id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: { triggerType: 'manual' } },
      {
        id: 'crew:crew-1',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-1', versionId: 'crew-v1' },
      },
      {
        id: 'output:main',
        type: 'output',
        position: { x: 900, y: 160 },
        data: { fields: [{ label: 'Answer', source: 'node', nodeId: 'crew:crew-1', path: 'output.final_answer' }] },
      },
    ],
    edges: [
      { id: 'edge:start:crew', source: 'start:main', target: 'crew:crew-1', type: 'flow' },
      { id: 'edge:crew:output', source: 'crew:crew-1', target: 'output:main', type: 'flow' },
    ],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  expect(FLOW_EDGE_STYLE).toEqual({ stroke: '#6952D6', strokeWidth: 2 });
  expect(screen.getByTestId('rf__node-crew:crew-1').querySelector('.react-flow__handle-right')).toHaveClass('!bg-cyan-400');
});

test('renders published crew tools inside the crew node without external tool nodes', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:crew-1',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-1', versionId: 'crew-v1' },
      },
    ],
    edges: [],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  expect(screen.getByText('Research Crew')).toBeInTheDocument();
  expect(screen.getByText('Research Agent')).toBeInTheDocument();
  expect(screen.getByText('Research Task')).toBeInTheDocument();
  expect(screen.getByText('Task tools')).toBeInTheDocument();
  expect(screen.getAllByText('Web Search')).toHaveLength(1);
  expect(screen.queryByTestId('rf__node-tool:crew%3Acrew-1%3Aweb_search')).not.toBeInTheDocument();
});

test('renders task tools as the effective agent plus task tool set', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:crew-1',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-1', versionId: 'crew-v1' },
      },
    ],
    edges: [],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrewWithAgentAndTaskTools]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:crew-1'));
  expect(crewNode.queryByText('Agent tools')).not.toBeInTheDocument();
  expect(crewNode.getByText('Task tools')).toBeInTheDocument();
  expect(crewNode.getByText('Directory Read')).toBeInTheDocument();
  expect(crewNode.getByText('Web Search')).toBeInTheDocument();
});

test('renders unresolved crew input pills inside the crew node', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-visual', versionId: 'crew-visual-v1' },
      },
    ],
    edges: [],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[visualCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:visual'));
  expect(crewNode.getByRole('button', { name: /bind card_news_slides/i })).toBeInTheDocument();
});

test('crew input binding dialog saves selected upstream output fields', () => {
  const changeDraftSpy = vi.fn();
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:content',
        type: 'crew',
        position: { x: 240, y: 160 },
        data: { assetId: 'crew-content', versionId: 'crew-content-v1' },
      },
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-visual', versionId: 'crew-visual-v1' },
      },
    ],
    edges: [{ id: 'edge:content:visual', source: 'crew:content', target: 'crew:visual', type: 'flow' }],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[contentCrew, visualCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={changeDraftSpy}
    />,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:visual'));
  fireEvent.click(crewNode.getByRole('button', { name: /bind card_news_slides/i }));
  expect(screen.getByRole('dialog', { name: /bind card_news_slides/i })).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText(/content crew \(crew:content\).*title_slide/i));
  fireEvent.click(screen.getByLabelText(/content crew .*body_slides/i));
  fireEvent.click(screen.getByLabelText(/content crew .*outro_slide/i));
  fireEvent.click(screen.getByRole('button', { name: /save binding/i }));

  expect(changeDraftSpy).toHaveBeenCalledWith(
    expect.objectContaining({
      nodes: expect.arrayContaining([
        expect.objectContaining({
          id: 'crew:visual',
          data: expect.objectContaining({
            inputMappings: expect.objectContaining({
              card_news_slides: {
                source: 'transform',
                inputType: 'text',
                nodeId: 'crew:content',
                paths: ['output.title_slide', 'output.body_slides', 'output.outro_slide'],
                transform: 'join_card_news_slides_v1',
                maxChars: 8000,
                overflow: 'fail',
              },
            }),
          }),
        }),
      ]),
    }),
  );
});

test('crew input binding dialog only lists ancestor crew output fields', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:content',
        type: 'crew',
        position: { x: 240, y: 160 },
        data: { assetId: 'crew-content', versionId: 'crew-content-v1' },
      },
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-visual', versionId: 'crew-visual-v1' },
      },
      {
        id: 'crew:unrelated',
        type: 'crew',
        position: { x: 900, y: 160 },
        data: { assetId: 'crew-unrelated', versionId: 'crew-unrelated-v1' },
      },
    ],
    edges: [{ id: 'edge:content:visual', source: 'crew:content', target: 'crew:visual', type: 'flow' }],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[contentCrew, visualCrew, unrelatedCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:visual'));
  fireEvent.click(crewNode.getByRole('button', { name: /bind card_news_slides/i }));

  expect(screen.getByLabelText(/content crew .*title_slide/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/unrelated crew .*title_slide/i)).not.toBeInTheDocument();
});

test('crew input binding dialog can switch selected source crew', () => {
  const changeDraftSpy = vi.fn();
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:content',
        type: 'crew',
        position: { x: 120, y: 160 },
        data: { assetId: 'crew-content', versionId: 'crew-content-v1' },
      },
      {
        id: 'crew:backup',
        type: 'crew',
        position: { x: 240, y: 320 },
        data: { assetId: 'crew-backup-content', versionId: 'crew-backup-content-v1' },
      },
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-visual', versionId: 'crew-visual-v1' },
      },
    ],
    edges: [
      { id: 'edge:content:visual', source: 'crew:content', target: 'crew:visual', type: 'flow' },
      { id: 'edge:backup:visual', source: 'crew:backup', target: 'crew:visual', type: 'flow' },
    ],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[contentCrew, backupContentCrew, visualCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={changeDraftSpy}
    />,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:visual'));
  fireEvent.click(crewNode.getByRole('button', { name: /bind card_news_slides/i }));
  fireEvent.click(screen.getByLabelText(/content crew \(crew:content\).*title_slide/i));
  fireEvent.click(screen.getByLabelText(/backup content crew .*outro_slide/i));
  fireEvent.click(screen.getByRole('button', { name: /save binding/i }));

  const nextDraft = changeDraftSpy.mock.calls[0][0] as FlowCanvasDraft;
  const visualNode = nextDraft.nodes.find((node) => node.id === 'crew:visual');
  const inputMappings = visualNode?.data.inputMappings as Record<string, unknown> | undefined;
  expect(inputMappings?.card_news_slides).toEqual({
    source: 'transform',
    inputType: 'text',
    nodeId: 'crew:backup',
    paths: ['output.outro_slide'],
    transform: 'join_card_news_slides_v1',
    maxChars: 8000,
    overflow: 'fail',
  });
});

test('crew input binding dialog replaces non-record input mappings on save', () => {
  const changeDraftSpy = vi.fn();
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:content',
        type: 'crew',
        position: { x: 240, y: 160 },
        data: { assetId: 'crew-content', versionId: 'crew-content-v1' },
      },
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-visual', versionId: 'crew-visual-v1', inputMappings: 'stale' } as any,
      },
    ],
    edges: [{ id: 'edge:content:visual', source: 'crew:content', target: 'crew:visual', type: 'flow' }],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[contentCrew, visualCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={changeDraftSpy}
    />,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:visual'));
  fireEvent.click(crewNode.getByRole('button', { name: /bind card_news_slides/i }));
  fireEvent.click(screen.getByLabelText(/content crew .*title_slide/i));
  fireEvent.click(screen.getByRole('button', { name: /save binding/i }));

  const nextDraft = changeDraftSpy.mock.calls[0][0] as FlowCanvasDraft;
  const visualNode = nextDraft.nodes.find((node) => node.id === 'crew:visual');
  expect(visualNode?.data.inputMappings).toEqual({
    card_news_slides: {
      source: 'transform',
      inputType: 'text',
      nodeId: 'crew:content',
      paths: ['output.title_slide'],
      transform: 'join_card_news_slides_v1',
      maxChars: 8000,
      overflow: 'fail',
    },
  });
});

test('crew input binding dialog traps focus and restores the opener on Escape', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      {
        id: 'crew:content',
        type: 'crew',
        position: { x: 240, y: 160 },
        data: { assetId: 'crew-content', versionId: 'crew-content-v1' },
      },
      {
        id: 'crew:visual',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-visual', versionId: 'crew-visual-v1' },
      },
    ],
    edges: [{ id: 'edge:content:visual', source: 'crew:content', target: 'crew:visual', type: 'flow' }],
  };

  render(
    <>
      <button type="button">Outside after</button>
      <FlowBuilderCanvas
        draft={draft}
        publishedCrews={[contentCrew, visualCrew]}
        onAddNode={() => undefined}
        onAddCrew={() => undefined}
        onSelectNode={() => undefined}
        onChangeDraft={() => undefined}
      />
    </>,
  );

  const crewNode = within(screen.getByTestId('rf__node-crew:visual'));
  const bindButton = crewNode.getByRole('button', { name: /bind card_news_slides/i });
  bindButton.focus();
  fireEvent.click(bindButton);

  const dialog = screen.getByRole('dialog', { name: /bind card_news_slides/i });
  fireEvent.click(screen.getByLabelText(/content crew \(crew:content\).*title_slide/i));

  const closeButton = screen.getByRole('button', { name: /close/i });
  const saveButton = screen.getByRole('button', { name: /save binding/i });

  expect(dialog).toHaveFocus();

  saveButton.focus();
  fireEvent.keyDown(saveButton, { key: 'Tab' });
  expect(closeButton).toHaveFocus();
  expect(screen.getByRole('button', { name: /outside after/i })).not.toHaveFocus();

  closeButton.focus();
  fireEvent.keyDown(closeButton, { key: 'Tab', shiftKey: true });
  expect(saveButton).toHaveFocus();

  fireEvent.keyDown(saveButton, { key: 'Escape' });
  expect(screen.queryByRole('dialog', { name: /bind card_news_slides/i })).not.toBeInTheDocument();
  expect(bindButton).toHaveFocus();
});

test('output node field dialog can add a field from a crew output schema', () => {
  const changeDraftSpy = vi.fn();
  const draft: FlowCanvasDraft = {
    selectedNodeId: 'output:main',
    nodes: [
      {
        id: 'crew:crew-1',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-1', versionId: 'crew-v1' },
      },
      {
        id: 'output:main',
        type: 'output',
        position: { x: 900, y: 160 },
        data: { fields: [] },
      },
    ],
    edges: [{ id: 'edge:crew:output', source: 'crew:crew-1', target: 'output:main', type: 'flow' }],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[
        {
          ...publishedCrew,
          runtimeSnapshot: {
            ...publishedCrew.runtimeSnapshot,
            output_schema: { type: 'object', properties: { final_answer: { type: 'string' } } },
          },
        },
      ]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={changeDraftSpy}
    />,
  );

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));
  expect(screen.getByRole('dialog', { name: /select output fields/i })).toBeInTheDocument();

  fireEvent.change(screen.getByRole('combobox', { name: /output field/i }), { target: { value: 'crew:crew-1|json.final_answer' } });
  fireEvent.click(screen.getByRole('button', { name: /add field/i }));
  expect(changeDraftSpy).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: /save fields/i }));

  expect(changeDraftSpy).toHaveBeenCalledWith(
    expect.objectContaining({
      nodes: expect.arrayContaining([
        expect.objectContaining({
          id: 'output:main',
          data: {
            fields: [{ label: 'Research Crew (crew:crew-1) / json.final_answer', source: 'node', nodeId: 'crew:crew-1', path: 'output.final_answer' }],
          },
        }),
      ]),
    }),
  );
});

test('extracts crew step summaries from runtime snapshots', () => {
  expect(getCrewStepSummaries(publishedCrew.runtimeSnapshot)).toEqual([
    {
      taskVersionId: 'task-v1',
      taskName: 'Research Task',
      agentName: 'Research Agent',
      toolKeys: ['web_search'],
      toolNames: ['Web Search'],
      agentToolNames: [],
      taskToolNames: ['Web Search'],
    },
  ]);
});

test('renders pinned crew entity tools inside the crew node when picker data lacks the version', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    entities: {
      crews: {
        'crew-v1': {
          asset_id: 'crew-1',
          version_id: 'crew-v1',
          version_no: 1,
          name: 'Pinned Research Crew',
          status: 'published',
          runtime_snapshot_json: publishedCrew.runtimeSnapshot,
        },
      },
    },
    nodes: [
      {
        id: 'crew:crew-1',
        type: 'crew',
        position: { x: 600, y: 160 },
        data: { assetId: 'crew-1', versionId: 'crew-v1' },
      },
    ],
    edges: [],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  expect(screen.getByText('Pinned Research Crew')).toBeInTheDocument();
  expect(screen.getByText('Research Agent')).toBeInTheDocument();
  expect(screen.getAllByText('Web Search')).toHaveLength(1);
  expect(screen.queryByTestId('rf__node-tool:crew%3Acrew-1%3Aweb_search')).not.toBeInTheDocument();
});

test('sizes crew flow nodes as a horizontal pipeline from the number of rendered steps', () => {
  const oneStep = getCrewFlowNodeDimensions(publishedCrew.runtimeSnapshot);
  const fourSteps = getCrewFlowNodeDimensions({
    ...publishedCrew.runtimeSnapshot,
    runtime_crew: { task_version_ids: ['task-v1', 'task-v2', 'task-v3', 'task-v4'] },
    runtime_tasks: {
      'task-v1': { task_name: 'Research Task' },
      'task-v2': { task_name: 'Draft Task' },
      'task-v3': { task_name: 'Review Task' },
      'task-v4': { task_name: 'Publish Task' },
    },
  });

  expect(fourSteps.width).toBeGreaterThan(oneStep.width);
  expect(fourSteps.height).toBeLessThanOrEqual(oneStep.height + 24);
  expect(fourSteps.width).toBeGreaterThan(fourSteps.height * 2);
});

test('connectFlowCanvasNodes ignores duplicate and self flow edges', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      { id: 'input:main', type: 'input', position: { x: 64, y: 160 }, data: {} },
      { id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: {} },
    ],
    edges: [{ id: 'edge:input:main:start:main', source: 'input:main', target: 'start:main', type: 'flow' }],
  };

  expect(connectFlowCanvasNodes(draft, { source: 'input:main', target: 'start:main', sourceHandle: null, targetHandle: null })).toBe(
    draft,
  );
  expect(connectFlowCanvasNodes(draft, { source: 'input:main', target: 'input:main', sourceHandle: null, targetHandle: null })).toBe(
    draft,
  );
});

test('connectFlowCanvasNodes appends a deterministic edge for a new node pair', () => {
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      { id: 'input:main', type: 'input', position: { x: 64, y: 160 }, data: {} },
      { id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: {} },
    ],
    edges: [],
  };

  expect(connectFlowCanvasNodes(draft, { source: 'input:main', target: 'start:main', sourceHandle: null, targetHandle: null })).toEqual({
    ...draft,
    edges: [{ id: 'edge:input:main:start:main', source: 'input:main', target: 'start:main', type: 'flow' }],
  });
});

test('flow canvas node menu removes a node and its connected edges', () => {
  const changeDraftSpy = vi.fn();
  const draft: FlowCanvasDraft = {
    selectedNodeId: null,
    nodes: [
      { id: 'start:main', type: 'start', position: { x: 320, y: 160 }, data: {} },
      { id: 'crew:crew-1', type: 'crew', position: { x: 600, y: 160 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
    ],
    edges: [{ id: 'edge:start:crew', source: 'start:main', target: 'crew:crew-1', type: 'flow' }],
  };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrew]}
      onAddNode={() => undefined}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={changeDraftSpy}
    />,
  );

  fireEvent.contextMenu(screen.getByTestId('rf__node-crew:crew-1'), { clientX: 300, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /remove node/i }));

  expect(changeDraftSpy).toHaveBeenCalledWith(
    expect.objectContaining({
      nodes: [expect.objectContaining({ id: 'start:main' })],
      edges: [],
    }),
  );
});

test('preserves graph metadata across document draft round trips', () => {
  const draft = flowGraphDocumentToCanvasDraft({
    schemaVersion: 1,
    layoutDirection: 'TB',
    viewport: { x: 120, y: 240, zoom: 0.75 },
    nodes: [
      {
        id: 'crew:research',
        type: 'crew',
        position: { x: 10, y: 20 },
        data: { versionId: 'crew-v2' },
      },
    ],
    edges: [],
    entities: {
      crews: {
        'crew-v1': {
          asset_id: 'crew-1',
          version_id: 'crew-v1',
          version_no: 1,
          name: 'Existing Crew',
          status: 'published',
          runtime_snapshot_json: { previous: true },
        },
        'crew-v2': {
          asset_id: 'crew-2',
          version_id: 'crew-v2',
          version_no: 1,
          name: 'Stale Crew',
          status: 'published',
          runtime_snapshot_json: { stale: true },
        },
      },
    },
  });

  const graph = draftToFlowGraph({
    draft,
    publishedCrews: [
      {
        assetId: 'crew-2',
        versionId: 'crew-v2',
        versionNo: 2,
        name: 'Updated Crew',
        description: 'Latest selected crew metadata',
        status: 'published',
        runtimeSnapshot: { updated: true },
      },
    ],
  });

  expect(graph.layoutDirection).toBe('TB');
  expect(graph.viewport).toEqual({ x: 120, y: 240, zoom: 0.75 });
  expect(graph.entities?.crews?.['crew-v1']).toEqual(
    expect.objectContaining({
      asset_id: 'crew-1',
      runtime_snapshot_json: { previous: true },
    }),
  );
  expect(graph.entities?.crews?.['crew-v2']).toEqual(
    expect.objectContaining({
      asset_id: 'crew-2',
      version_no: 2,
      name: 'Updated Crew',
      runtime_snapshot_json: { updated: true },
    }),
  );
});

test.each([
  ['input', /add input/i],
  ['start', /add start/i],
  ['router', /add router/i],
  ['hitl', /add hitl/i],
  ['output', /add output/i],
] satisfies Array<[FlowNodeKind, RegExp]>)('flow canvas context menu can request adding a %s node', (kind, menuLabel) => {
  const addNodeSpy = vi.fn();
  const draft: FlowCanvasDraft = { selectedNodeId: null, nodes: [], edges: [] };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[]}
      onAddNode={addNodeSpy}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  fireEvent.contextMenu(screen.getByLabelText('Flow canvas'), { clientX: 300, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: menuLabel }));
  expect(addNodeSpy).toHaveBeenCalledWith(kind, expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }));
});

test('flow canvas context menu can request adding a crew node through the crew picker path', () => {
  const addNodeSpy = vi.fn();
  const addCrewSpy = vi.fn();
  const draft: FlowCanvasDraft = { selectedNodeId: null, nodes: [], edges: [] };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrew]}
      onAddNode={addNodeSpy}
      onAddCrew={addCrewSpy}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  fireEvent.contextMenu(screen.getByLabelText('Flow canvas'), { clientX: 300, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /research crew/i }));
  expect(addCrewSpy).toHaveBeenCalledWith(expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }), publishedCrew);
  expect(addNodeSpy).not.toHaveBeenCalled();
});

test.each([
  ['input', /add input/i],
  ['router', /add router/i],
] satisfies Array<[FlowNodeKind, RegExp]>)('flow canvas toolbar can request adding a %s node accessibly', (kind, buttonLabel) => {
  const addNodeSpy = vi.fn();
  const draft: FlowCanvasDraft = { selectedNodeId: null, nodes: [], edges: [] };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[]}
      onAddNode={addNodeSpy}
      onAddCrew={() => undefined}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: buttonLabel }));
  expect(addNodeSpy).toHaveBeenCalledWith(kind, expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }));
});

test('flow canvas context menu passes the clicked flow position to the crew picker path', () => {
  const addCrewSpy = vi.fn();
  const draft: FlowCanvasDraft = { selectedNodeId: null, nodes: [], edges: [] };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrew]}
      onAddNode={() => undefined}
      onAddCrew={addCrewSpy}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
    />,
  );

  fireEvent.contextMenu(screen.getByLabelText('Flow canvas'), { clientX: 300, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /research crew/i }));
  expect(addCrewSpy).toHaveBeenCalledWith(expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }), publishedCrew);
});

test('top add crew affordance opens the same crew picker path', () => {
  const addCrewSpy = vi.fn();
  const draft: FlowCanvasDraft = { selectedNodeId: null, nodes: [], edges: [] };

  render(
    <FlowBuilderCanvas
      draft={draft}
      publishedCrews={[publishedCrew]}
      onAddNode={() => undefined}
      onAddCrew={addCrewSpy}
      onSelectNode={() => undefined}
      onChangeDraft={() => undefined}
      showTopAddCrew
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: /add crew/i }));
  expect(addCrewSpy).toHaveBeenCalledWith(expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }), publishedCrew);
});

test('output node context menu opens field selection with raw option', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        { id: 'start:main', type: 'start', position: { x: 0, y: 0 }, data: { triggerType: 'manual' } },
        { id: 'crew:research', type: 'crew', position: { x: 240, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'output:main', type: 'output', position: { x: 520, y: 0 }, data: { fields: [] } },
      ],
      edges: [
        { id: 'edge:start:crew', source: 'start:main', target: 'crew:research', type: 'flow' },
        { id: 'edge:crew:output', source: 'crew:research', target: 'output:main', type: 'flow' },
      ],
    } as any);

    return (
      <>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[
            {
              assetId: 'crew-1',
              versionId: 'crew-v1',
              versionNo: 1,
              name: 'Research Crew',
              description: 'Research',
              status: 'published',
              runtimeSnapshot: {},
            },
          ]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
        <pre data-testid="draft-state">{JSON.stringify(draft)}</pre>
      </>
    );
  }

  function getOutputFields() {
    const draftState = JSON.parse(screen.getByTestId('draft-state').textContent ?? '{}');
    const outputNode = draftState.nodes.find((node: any) => node.id === 'output:main');
    return outputNode?.data?.fields;
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));

  expect(screen.getByRole('dialog', { name: /select output fields/i })).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /research crew.*\/ raw/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('checkbox', { name: /research crew.*\/ raw/i }));
  fireEvent.click(screen.getByRole('button', { name: /save fields/i }));

  expect(getOutputFields()).toEqual([
    { label: 'Research Crew (crew:research) / raw', source: 'node', nodeId: 'crew:research', path: 'output.raw' },
  ]);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /clear output fields/i }));
  expect(getOutputFields()).toEqual([]);
});

test('hitl node context menu configures review behavior and displays policy metadata', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        {
          id: 'hitl:review',
          type: 'hitl',
          position: { x: 240, y: 0 },
          data: {
            prompt: '',
            allowedDecisions: ['approved', 'needs_revision', 'rejected'],
            onNeedsRevision: 'retry_previous',
            feedbackPropagation: 'needs_revision_only',
            maxAttempts: 3,
            metadata: { reviewerGroup: 'qa-reviewers' },
          },
        },
      ],
      edges: [],
    } as any);

    return (
      <>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
        <pre data-testid="draft-state">{JSON.stringify(draft)}</pre>
      </>
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-hitl:review'), { clientX: 420, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /configure hitl/i }));

  expect(screen.getByRole('dialog', { name: /configure hitl/i })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/review prompt/i), { target: { value: 'Review the crew output.' } });
  fireEvent.change(screen.getByLabelText(/max attempts/i), { target: { value: '4' } });
  fireEvent.change(screen.getByLabelText(/needs revision behavior/i), {
    target: { value: 'continue_with_feedback' },
  });
  fireEvent.change(screen.getByLabelText(/feedback propagation/i), {
    target: { value: 'approved_and_needs_revision' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save hitl/i }));

  expect(screen.queryByRole('dialog', { name: /configure hitl/i })).not.toBeInTheDocument();
  expect(screen.getByText(/continue with feedback/i)).toBeInTheDocument();
  expect(screen.getByText(/4 attempts/i)).toBeInTheDocument();

  const draftState = JSON.parse(screen.getByTestId('draft-state').textContent ?? '{}');
  expect(draftState.nodes[0].data).toEqual(
    expect.objectContaining({
      prompt: 'Review the crew output.',
      allowedDecisions: ['approved', 'needs_revision', 'rejected'],
      onNeedsRevision: 'continue_with_feedback',
      feedbackPropagation: 'approved_and_needs_revision',
      maxAttempts: 4,
      metadata: { reviewerGroup: 'qa-reviewers' },
    }),
  );
});

test('hitl node save normalizes invalid max attempts while preserving existing data', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        {
          id: 'hitl:review',
          type: 'hitl',
          position: { x: 240, y: 0 },
          data: {
            prompt: 'Check the final answer.',
            allowedDecisions: ['approved', 'needs_revision', 'rejected'],
            onNeedsRevision: 'retry_previous',
            feedbackPropagation: 'needs_revision_only',
            maxAttempts: 5,
            metadata: { reviewerGroup: 'qa-reviewers' },
          },
        },
      ],
      edges: [],
    } as any);

    return (
      <>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
        <pre data-testid="draft-state">{JSON.stringify(draft)}</pre>
      </>
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-hitl:review'), { clientX: 420, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /configure hitl/i }));

  fireEvent.change(screen.getByLabelText(/max attempts/i), { target: { value: '0' } });
  fireEvent.click(screen.getByRole('button', { name: /save hitl/i }));

  const draftState = JSON.parse(screen.getByTestId('draft-state').textContent ?? '{}');
  expect(draftState.nodes[0].data).toEqual(
    expect.objectContaining({
      prompt: 'Check the final answer.',
      allowedDecisions: ['approved', 'needs_revision', 'rejected'],
      onNeedsRevision: 'retry_previous',
      feedbackPropagation: 'needs_revision_only',
      maxAttempts: 3,
      metadata: { reviewerGroup: 'qa-reviewers' },
    }),
  );
});

test('output node field dialog cancel discards raw field edits', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        { id: 'start:main', type: 'start', position: { x: 0, y: 0 }, data: { triggerType: 'manual' } },
        { id: 'crew:research', type: 'crew', position: { x: 240, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'output:main', type: 'output', position: { x: 520, y: 0 }, data: { fields: [] } },
      ],
      edges: [
        { id: 'edge:start:crew', source: 'start:main', target: 'crew:research', type: 'flow' },
        { id: 'edge:crew:output', source: 'crew:research', target: 'output:main', type: 'flow' },
      ],
    } as any);

    return (
      <>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[
            {
              assetId: 'crew-1',
              versionId: 'crew-v1',
              versionNo: 1,
              name: 'Research Crew',
              description: 'Research',
              status: 'published',
              runtimeSnapshot: {},
            },
          ]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
        <pre data-testid="draft-state">{JSON.stringify(draft)}</pre>
      </>
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));
  fireEvent.click(screen.getByRole('checkbox', { name: /research crew.*\/ raw/i }));
  fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

  const draftState = JSON.parse(screen.getByTestId('draft-state').textContent ?? '{}');
  const outputNode = draftState.nodes.find((node: any) => node.id === 'output:main');
  expect(outputNode.data.fields).toEqual([]);
});

test('output node field dialog add field button stores raw label and path', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        { id: 'start:main', type: 'start', position: { x: 0, y: 0 }, data: { triggerType: 'manual' } },
        { id: 'crew:research', type: 'crew', position: { x: 240, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'output:main', type: 'output', position: { x: 520, y: 0 }, data: { fields: [] } },
      ],
      edges: [
        { id: 'edge:start:crew', source: 'start:main', target: 'crew:research', type: 'flow' },
        { id: 'edge:crew:output', source: 'crew:research', target: 'output:main', type: 'flow' },
      ],
    } as any);

    return (
      <>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[
            {
              assetId: 'crew-1',
              versionId: 'crew-v1',
              versionNo: 1,
              name: 'Research Crew',
              description: 'Research',
              status: 'published',
              runtimeSnapshot: {},
            },
          ]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
        <pre data-testid="draft-state">{JSON.stringify(draft)}</pre>
      </>
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));
  fireEvent.click(screen.getByRole('button', { name: /add field/i }));
  fireEvent.click(screen.getByRole('button', { name: /save fields/i }));

  const draftState = JSON.parse(screen.getByTestId('draft-state').textContent ?? '{}');
  const outputNode = draftState.nodes.find((node: any) => node.id === 'output:main');
  expect(outputNode.data.fields).toEqual([
    { label: 'Research Crew (crew:research) / raw', source: 'node', nodeId: 'crew:research', path: 'output.raw' },
  ]);
});

test('output field dialog stores distinct labels for duplicate published crew raw outputs', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        { id: 'start:main', type: 'start', position: { x: 0, y: 0 }, data: { triggerType: 'manual' } },
        { id: 'crew:research-a', type: 'crew', position: { x: 240, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'crew:research-b', type: 'crew', position: { x: 240, y: 180 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'output:main', type: 'output', position: { x: 520, y: 0 }, data: { fields: [] } },
      ],
      edges: [
        { id: 'edge:start:crew-a', source: 'start:main', target: 'crew:research-a', type: 'flow' },
        { id: 'edge:crew-a:crew-b', source: 'crew:research-a', target: 'crew:research-b', type: 'flow' },
        { id: 'edge:crew-b:output', source: 'crew:research-b', target: 'output:main', type: 'flow' },
      ],
    } as any);

    return (
      <>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[{ ...publishedCrew, runtimeSnapshot: {} }]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
        <pre data-testid="draft-state">{JSON.stringify(draft)}</pre>
      </>
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));
  for (const rawCheckbox of screen.getAllByRole('checkbox', { name: /research crew.*\/ raw/i })) {
    fireEvent.click(rawCheckbox);
  }
  fireEvent.click(screen.getByRole('button', { name: /save fields/i }));

  const draftState = JSON.parse(screen.getByTestId('draft-state').textContent ?? '{}');
  const outputNode = draftState.nodes.find((node: any) => node.id === 'output:main');
  expect(outputNode.data.fields).toEqual([
    { label: 'Research Crew (crew:research-a) / raw', source: 'node', nodeId: 'crew:research-a', path: 'output.raw' },
    { label: 'Research Crew (crew:research-b) / raw', source: 'node', nodeId: 'crew:research-b', path: 'output.raw' },
  ]);
});

test('output field dialog closes on Escape', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        { id: 'start:main', type: 'start', position: { x: 0, y: 0 }, data: { triggerType: 'manual' } },
        { id: 'crew:research', type: 'crew', position: { x: 240, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'output:main', type: 'output', position: { x: 520, y: 0 }, data: { fields: [] } },
      ],
      edges: [
        { id: 'edge:start:crew', source: 'start:main', target: 'crew:research', type: 'flow' },
        { id: 'edge:crew:output', source: 'crew:research', target: 'output:main', type: 'flow' },
      ],
    } as any);

    return (
      <FlowBuilderCanvas
        draft={draft}
        publishedCrews={[{ ...publishedCrew, runtimeSnapshot: {} }]}
        onAddNode={() => undefined}
        onAddCrew={() => undefined}
        onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
        onChangeDraft={setDraft}
      />
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));
  const dialog = screen.getByRole('dialog', { name: /select output fields/i });

  expect(dialog).toHaveFocus();
  fireEvent.keyDown(dialog, { key: 'Escape' });

  expect(screen.queryByRole('dialog', { name: /select output fields/i })).not.toBeInTheDocument();
});

test('output field dialog traps Tab focus within controls', () => {
  function FlowHarness() {
    const [draft, setDraft] = useState({
      selectedNodeId: null,
      nodes: [
        { id: 'start:main', type: 'start', position: { x: 0, y: 0 }, data: { triggerType: 'manual' } },
        { id: 'crew:research', type: 'crew', position: { x: 240, y: 0 }, data: { assetId: 'crew-1', versionId: 'crew-v1' } },
        { id: 'output:main', type: 'output', position: { x: 520, y: 0 }, data: { fields: [] } },
      ],
      edges: [
        { id: 'edge:start:crew', source: 'start:main', target: 'crew:research', type: 'flow' },
        { id: 'edge:crew:output', source: 'crew:research', target: 'output:main', type: 'flow' },
      ],
    } as any);

    return (
      <>
        <button type="button">Outside after</button>
        <FlowBuilderCanvas
          draft={draft}
          publishedCrews={[{ ...publishedCrew, runtimeSnapshot: {} }]}
          onAddNode={() => undefined}
          onAddCrew={() => undefined}
          onSelectNode={(nodeId) => setDraft((current: any) => ({ ...current, selectedNodeId: nodeId }))}
          onChangeDraft={setDraft}
        />
      </>
    );
  }

  render(<FlowHarness />);

  fireEvent.contextMenu(screen.getByTestId('rf__node-output:main'), { clientX: 520, clientY: 220 });
  fireEvent.click(screen.getByRole('menuitem', { name: /select output fields/i }));

  const rawCheckbox = screen.getByRole('checkbox', { name: /research crew.*\/ raw/i });
  const closeButton = screen.getByRole('button', { name: /close/i });
  const saveButton = screen.getByRole('button', { name: /save fields/i });

  saveButton.focus();
  fireEvent.keyDown(saveButton, { key: 'Tab' });
  expect(closeButton).toHaveFocus();
  expect(rawCheckbox).not.toHaveFocus();
  expect(screen.getByRole('button', { name: /outside after/i })).not.toHaveFocus();
});
