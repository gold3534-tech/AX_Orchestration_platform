import { Handle, Position, type Node, type NodeProps } from '@xyflow/react';
import { CanvasNodeLabel, CanvasNodeTitle } from '../../../components/canvas';
import type { FlowBuilderNodeData, FlowNodeKind } from '../flowGraphTypes';
import { getCrewFlowNodeDimensions, getCrewStepSummaries } from './flowCanvasHelpers';

const COMPACT_FLOW_NODE_WIDTH = 250;
const COMPACT_FLOW_NODE_HEIGHT = 116;
const TOOL_FLOW_NODE_WIDTH = 190;
const TOOL_FLOW_NODE_HEIGHT = 78;

export const CORE_NODE_KINDS: FlowNodeKind[] = ['input', 'start', 'crew', 'router', 'hitl', 'execution_action', 'output'];

const SIMPLE_FLOW_NODE_TONE = 'border-[#7a5739] bg-[#fffaf0] text-[#22170f]';

const nodeToneClasses: Record<FlowNodeKind, string> = {
  input: SIMPLE_FLOW_NODE_TONE,
  start: SIMPLE_FLOW_NODE_TONE,
  crew: SIMPLE_FLOW_NODE_TONE,
  router: SIMPLE_FLOW_NODE_TONE,
  hitl: SIMPLE_FLOW_NODE_TONE,
  output: SIMPLE_FLOW_NODE_TONE,
  tool: SIMPLE_FLOW_NODE_TONE,
  execution_action: SIMPLE_FLOW_NODE_TONE,
};

export function nodeLabel(kind: FlowNodeKind) {
  const labels: Record<FlowNodeKind, string> = {
    input: 'Input',
    start: 'Start',
    crew: 'Crew',
    router: 'Router',
    hitl: 'HITL',
    output: 'Output',
    tool: 'Tool',
    execution_action: 'Action',
  };

  return labels[kind];
}

export function nodeDimensions(kind: FlowNodeKind, runtimeSnapshot?: unknown) {
  if (kind === 'crew') {
    return getCrewFlowNodeDimensions(runtimeSnapshot);
  }

  if (kind === 'tool') {
    return { width: TOOL_FLOW_NODE_WIDTH, height: TOOL_FLOW_NODE_HEIGHT };
  }

  return { width: COMPACT_FLOW_NODE_WIDTH, height: COMPACT_FLOW_NODE_HEIGHT };
}

function formatHitlAttempts(value: unknown) {
  const attempts = typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.floor(value) : 3;

  return `${attempts} ${attempts === 1 ? 'attempt' : 'attempts'}`;
}

function formatHitlNeedsRevisionBehavior(value: unknown) {
  return value === 'continue_with_feedback' ? 'Continue with feedback' : 'Retry previous';
}

export function FlowNodeCard({ data, selected, isConnectable }: NodeProps<Node<FlowBuilderNodeData>>) {
  const nodeData = data as FlowBuilderNodeData;
  const toneClass = nodeToneClasses[nodeData.kind];
  const selectedClass = selected ? 'ring-2 ring-[#2f9b96] ring-offset-2 ring-offset-[#f8e8c8]' : '';
  const detail =
    nodeData.kind === 'crew'
      ? typeof nodeData.versionId === 'string'
        ? `Pinned ${nodeData.versionId.slice(0, 8)}`
        : 'Select a published crew'
        : nodeData.kind === 'router'
          ? 'Optional branch rules'
        : nodeData.kind === 'hitl'
          ? `${formatHitlNeedsRevisionBehavior(nodeData.onNeedsRevision)} • ${formatHitlAttempts(nodeData.maxAttempts)}`
          : nodeData.kind === 'execution_action'
            ? String(nodeData.actionKey ?? 'Select an action')
          : nodeData.kind === 'input'
            ? 'Flow state input'
            : nodeData.kind === 'output'
              ? 'Final state output'
              : nodeData.kind === 'tool'
                ? 'Read-only runtime tool'
                : 'Manual trigger';

  return (
    <div
      className={`relative h-full w-full overflow-hidden rounded-md border-2 px-4 py-4 text-left shadow-[5px_5px_0_#7a5739] ${toneClass} ${selectedClass}`}
    >
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        isConnectable={isConnectable}
        className="!z-20 !h-5 !w-5 !rounded-sm !border-2 !border-[#5b3424] !bg-[#ef8b2c]"
      />
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        isConnectable={isConnectable}
        className="!z-20 !h-5 !w-5 !rounded-sm !border-2 !border-[#5b3424] !bg-[#2f9b96]"
      />
      <CanvasNodeLabel className="text-[#2f9b96]">{nodeLabel(nodeData.kind)}</CanvasNodeLabel>
      <CanvasNodeTitle>{nodeData.label}</CanvasNodeTitle>
      <p className="mt-1 truncate text-xs leading-5 text-stone-600">{detail}</p>
    </div>
  );
}

export function CrewFlowNodeCard({ data, selected, isConnectable }: NodeProps<Node<FlowBuilderNodeData>>) {
  const nodeData = data as FlowBuilderNodeData;
  const steps = getCrewStepSummaries(nodeData.runtimeSnapshot);
  const missingInputs = nodeData.missingInputs ?? [];

  function renderToolNames(toolNames: string[]) {
    if (toolNames.length === 0) {
      return null;
    }

    const visibleToolNames = toolNames.slice(0, 2);
    const remainingToolCount = Math.max(0, toolNames.length - visibleToolNames.length);

    return (
      <div className="mt-auto min-w-0">
        <CanvasNodeLabel className="mb-1 text-amber-700">Task tools</CanvasNodeLabel>
        <div className="flex min-w-0 items-center gap-1.5 text-[10px] font-semibold text-amber-800">
          {visibleToolNames.map((toolName) => (
            <span key={toolName} className="truncate rounded border border-[#7a5739]/40 bg-[#ffe6b3] px-2 py-0.5">
              {toolName}
            </span>
          ))}
          {remainingToolCount > 0 ? (
            <span className="shrink-0 rounded border border-[#7a5739]/40 bg-[#fffaf0] px-1.5 py-0.5">+{remainingToolCount}</span>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`relative h-full w-full overflow-hidden rounded-md border-2 bg-[#fffaf0] shadow-[6px_6px_0_#7a5739] ${
        selected ? 'border-[#2f9b96] ring-2 ring-[#2f9b96] ring-offset-2 ring-offset-[#f8e8c8]' : 'border-[#7a5739]'
      }`}
    >
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        isConnectable={isConnectable}
        className="!z-20 !h-5 !w-5 !rounded-sm !border-2 !border-[#5b3424] !bg-[#ef8b2c]"
      />
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        isConnectable={isConnectable}
        className="!z-20 !h-5 !w-5 !rounded-sm !border-2 !border-[#5b3424] !bg-[#2f9b96]"
      />
      <div className="flex items-start justify-between gap-4 border-b-2 border-[#5b3424] bg-[#2f9b96] px-4 py-3">
        <div className="min-w-0">
          <CanvasNodeLabel className="text-white/70">Crew</CanvasNodeLabel>
          <p className="mt-1 truncate text-sm font-semibold text-white">{nodeData.label}</p>
        </div>
        <p className="shrink-0 rounded border border-white/40 bg-white/15 px-2.5 py-1 text-xs font-semibold text-white">
          {steps.length} step{steps.length === 1 ? '' : 's'}
        </p>
      </div>

      {missingInputs.length > 0 ? (
        <div className="border-b border-rose-100 bg-rose-50/70 px-4 py-2">
          <div className="flex flex-wrap gap-1.5">
            {missingInputs.map((inputName) => (
              <button
                key={inputName}
                type="button"
                aria-label={`Bind ${inputName}`}
                onClick={(event) => {
                  event.stopPropagation();
                  nodeData.onOpenInputBinding?.(inputName);
                }}
                className="rounded border border-rose-300 bg-[#fffaf0] px-2.5 py-1 text-[11px] font-semibold text-rose-700 shadow-sm hover:bg-rose-100"
              >
                Bind {inputName}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="p-3">
        {steps.length > 0 ? (
          <ol className="flex h-[212px] items-stretch gap-2">
            {steps.map((step, index) => (
              <li key={step.taskVersionId} className="relative min-w-0 flex-1">
                {index < steps.length - 1 ? <span className="absolute left-[calc(100%-2px)] top-6 z-0 h-0.5 w-3 bg-[#7a5739]" /> : null}
                <div className="relative z-10 flex h-full min-w-0 flex-col rounded border border-[#7a5739]/50 bg-[#fff6df] p-2 shadow-[2px_2px_0_rgba(122,87,57,0.35)]">
                  <div className="flex items-center gap-2">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded bg-[#ef8b2c] text-[11px] font-bold text-white">
                      {index + 1}
                    </span>
                    <CanvasNodeLabel className="truncate text-cyan-700">Step {index + 1}</CanvasNodeLabel>
                  </div>
                  <div className="mt-2 grid min-w-0 gap-1.5">
                    <div className="min-w-0 rounded border border-[#2f9b96]/50 bg-[#e6f6f2] px-2 py-1">
                      <CanvasNodeLabel className="text-cyan-700">Agent</CanvasNodeLabel>
                      <p className="mt-0.5 truncate text-[11px] font-semibold text-stone-950">{step.agentName}</p>
                    </div>
                    <div className="min-w-0 rounded border border-[#7a5739]/40 bg-[#fffaf0] px-2 py-1">
                      <CanvasNodeLabel className="text-emerald-700">Task</CanvasNodeLabel>
                      <p className="mt-0.5 truncate text-[11px] font-semibold text-stone-950">{step.taskName}</p>
                    </div>
                  </div>
                  {renderToolNames(step.toolNames)}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <div className="rounded-md border-2 border-dashed border-[#7a5739] bg-[#fff6df] p-4">
            <p className="text-sm font-semibold text-stone-900">Runtime details unavailable</p>
            <p className="mt-1 text-xs leading-5 text-stone-500">Publish the Crew with a runtime snapshot to inspect agents, tasks, and tools here.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export const nodeTypes = {
  input: FlowNodeCard,
  start: FlowNodeCard,
  crew: CrewFlowNodeCard,
  router: FlowNodeCard,
  hitl: FlowNodeCard,
  output: FlowNodeCard,
  tool: FlowNodeCard,
  execution_action: FlowNodeCard,
};
