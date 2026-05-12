import { Handle, NodeResizeControl, Position, type NodeProps } from '@xyflow/react';
import {
  CANVAS_SUBTITLE_CLAMP_STYLE,
  CanvasAssetNodeCard,
  CanvasNodeLabel,
  CanvasNodeTitle,
  CanvasToolChips,
  getCanvasTriangleHandleClass,
} from '../../../components/canvas';
import type {
  CrewGraphAgentNodeData,
  CrewGraphCrewNodeData,
  CrewGraphPlaceholderNodeData,
  CrewGraphTaskNodeData,
} from '../crewGraphTypes';

export const AGENT_ASSIGNMENT_SOURCE_HANDLE = 'agent-assignment-source';
export const AGENT_ASSIGNMENT_TARGET_HANDLE = 'agent-assignment-target';
export const TASK_CONTEXT_SOURCE_HANDLE = 'task-context-source';
export const TASK_CONTEXT_TARGET_HANDLE = 'task-context-target';
export const TASK_SEQUENCE_SOURCE_HANDLE = 'task-sequence-source';
export const TASK_SEQUENCE_TARGET_HANDLE = 'task-sequence-target';

const CREW_CONTAINER_MIN_WIDTH = 720;
const CREW_CONTAINER_MIN_HEIGHT = 360;

export function CrewContainerNode({ data, selected }: NodeProps) {
  const crew = data as CrewGraphCrewNodeData;
  if (!crew || crew.kind !== 'crew') return null;

  return (
    <div className={`relative h-full w-full rounded-md border-2 bg-[#fff6df]/75 shadow-inner ${selected ? 'border-[#2f9b96]' : 'border-[#7a5739]'}`}>
      <NodeResizeControl
        minWidth={CREW_CONTAINER_MIN_WIDTH}
        minHeight={CREW_CONTAINER_MIN_HEIGHT}
        position="bottom-right"
        className="nodrag nowheel !bottom-2 !right-2 !h-5 !w-5 !translate-x-0 !translate-y-0 !border-0 !bg-transparent"
        style={{ left: 'auto', top: 'auto', right: 8, bottom: 8, translate: '0 0' }}
      >
        <div className="relative h-5 w-5 rounded-br border-b-2 border-r-2 border-[#2f9b96] bg-[#fffaf0] shadow-sm">
          <div className="absolute bottom-1 right-1 h-2.5 w-2.5 border-b border-r border-[#2f9b96]/80" />
        </div>
      </NodeResizeControl>
      <div className="flex items-center justify-between rounded-t border-b-2 border-[#5b3424] bg-[#2f9b96] px-4 py-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/75">Crew</p>
          <p className="mt-1 text-sm font-semibold text-white">{crew.name}</p>
        </div>
        <p className="max-w-md truncate text-xs text-white/75">{crew.subtitle}</p>
      </div>
    </div>
  );
}

export function PlaceholderNode({ data, selected }: NodeProps) {
  const placeholder = data as CrewGraphPlaceholderNodeData;
  if (!placeholder || placeholder.kind !== 'placeholder') return null;

  return (
    <div
      className={`w-[220px] rounded-md border-2 border-dashed bg-[#fffaf0] px-3 py-3 text-stone-600 shadow-[4px_4px_0_#7a5739] ${
        selected ? 'border-[#2f9b96] ring-2 ring-[#2f9b96] ring-offset-2 ring-offset-[#f8e8c8]' : 'border-[#7a5739]'
      }`}
    >
      <CanvasNodeLabel>Placeholder</CanvasNodeLabel>
      <p className="mt-1 text-sm font-semibold text-stone-950">{placeholder.label}</p>
      <p className="mt-1 text-xs leading-5 text-stone-500">{placeholder.subtitle}</p>
    </div>
  );
}

export function AgentNode({ data, selected }: NodeProps) {
  const agent = data as CrewGraphAgentNodeData;
  if (!agent || agent.kind !== 'agent') return null;

  return (
    <CanvasAssetNodeCard
      className={`relative rounded-md border-2 border-[#2f9b96] bg-[#e6f6f2] px-3 py-3 shadow-[4px_4px_0_#7a5739] ${
        selected ? 'ring-2 ring-[#2f9b96] ring-offset-2 ring-offset-[#f8e8c8]' : ''
      }`}
      fillColor="#ecfeff"
    >
      <Handle
        id={AGENT_ASSIGNMENT_SOURCE_HANDLE}
        type="source"
        position={Position.Top}
        className={getCanvasTriangleHandleClass('red', 'output-up')}
      />
      <CanvasNodeLabel className="text-cyan-700">Agent</CanvasNodeLabel>
      <CanvasNodeTitle>{agent.name}</CanvasNodeTitle>
      <p className="mt-1 text-xs leading-5 text-stone-600" style={CANVAS_SUBTITLE_CLAMP_STYLE}>{agent.subtitle}</p>
      <CanvasToolChips names={agent.toolNames} />
    </CanvasAssetNodeCard>
  );
}

export function TaskNode({ data, selected }: NodeProps) {
  const task = data as CrewGraphTaskNodeData;
  if (!task || task.kind !== 'task') return null;

  return (
    <CanvasAssetNodeCard
      className={`relative rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-3 shadow-[4px_4px_0_#7a5739] ${
        selected ? 'ring-2 ring-[#ef8b2c] ring-offset-2 ring-offset-[#f8e8c8]' : ''
      }`}
      fillColor="#ecfdf5"
    >
      <Handle
        id={TASK_CONTEXT_TARGET_HANDLE}
        type="target"
        position={Position.Left}
        className={getCanvasTriangleHandleClass('orange', 'input-right')}
        style={{ top: '34%' }}
      />
      <Handle
        id={TASK_CONTEXT_SOURCE_HANDLE}
        type="source"
        position={Position.Right}
        className={getCanvasTriangleHandleClass('orange', 'output-right')}
        style={{ top: '34%' }}
      />
      <Handle
        id={TASK_SEQUENCE_TARGET_HANDLE}
        type="target"
        position={Position.Left}
        className={getCanvasTriangleHandleClass('green', 'input-right')}
        style={{ top: '66%' }}
      />
      <Handle
        id={TASK_SEQUENCE_SOURCE_HANDLE}
        type="source"
        position={Position.Right}
        className={getCanvasTriangleHandleClass('green', 'output-right')}
        style={{ top: '66%' }}
      />
      <Handle
        id={AGENT_ASSIGNMENT_TARGET_HANDLE}
        type="target"
        position={Position.Bottom}
        className={getCanvasTriangleHandleClass('red', 'input-up')}
      />
      <CanvasNodeLabel className="text-emerald-700">Task</CanvasNodeLabel>
      <CanvasNodeTitle>{task.name}</CanvasNodeTitle>
      <p className="mt-1 text-xs leading-5 text-stone-600" style={CANVAS_SUBTITLE_CLAMP_STYLE}>{task.subtitle}</p>
      <CanvasToolChips names={task.toolNames} />
    </CanvasAssetNodeCard>
  );
}
