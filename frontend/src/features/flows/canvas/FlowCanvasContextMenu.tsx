import type { XYPosition } from '@xyflow/react';
import type { PublishedCrewOption } from '../hooks';
import type { FlowGraphNodeId, FlowNodeKind } from '../flowGraphTypes';
import { CORE_NODE_KINDS, nodeLabel } from './FlowCanvasNodes';

export type FlowCanvasMenuState = {
  screenX: number;
  screenY: number;
  flowPosition: XYPosition;
  nodeId?: FlowGraphNodeId;
};

type FlowCanvasMenuNode = {
  id: FlowGraphNodeId;
  type: FlowNodeKind;
};

export function FlowCanvasContextMenu({
  menu,
  nodes,
  selectedNodeId,
  publishedCrews,
  onAddNode,
  onAddCrew,
  onConfigureHitl,
  onConfigureAction,
  onSelectOutputFields,
  onClearOutputFields,
  onRemoveNode,
  onRemoveSelectedNode,
}: {
  menu: FlowCanvasMenuState;
  nodes: FlowCanvasMenuNode[];
  selectedNodeId: FlowGraphNodeId | null;
  publishedCrews: PublishedCrewOption[];
  onAddNode: (kind: FlowNodeKind) => void;
  onAddCrew: (crew: PublishedCrewOption) => void;
  onConfigureHitl: (nodeId: FlowGraphNodeId) => void;
  onConfigureAction: (nodeId: FlowGraphNodeId) => void;
  onSelectOutputFields: (nodeId: FlowGraphNodeId) => void;
  onClearOutputFields: (nodeId: FlowGraphNodeId) => void;
  onRemoveNode: (nodeId: FlowGraphNodeId) => void;
  onRemoveSelectedNode: () => void;
}) {
  const menuNode = menu.nodeId ? nodes.find((node) => node.id === menu.nodeId) : null;

  return (
    <div
      role="menu"
      aria-label={menu.nodeId ? 'Flow node menu' : 'Add flow node'}
      className="absolute z-20 grid w-60 gap-1 rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-2 shadow-[5px_5px_0_#7a5739]"
      style={{
        left: Math.min(Math.max(12, menu.screenX), 820),
        top: Math.min(Math.max(12, menu.screenY), 420),
      }}
    >
      {menu.nodeId ? (
        <>
          {menuNode?.type === 'output' ? (
            <>
              <button
                type="button"
                role="menuitem"
                onClick={() => onSelectOutputFields(menu.nodeId as FlowGraphNodeId)}
                className="rounded-xl px-3 py-2 text-left text-sm font-medium text-emerald-800 hover:bg-emerald-50"
              >
                Select output fields
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => onClearOutputFields(menu.nodeId as FlowGraphNodeId)}
                className="rounded-xl px-3 py-2 text-left text-sm font-medium text-stone-700 hover:bg-stone-100"
              >
                Clear output fields
              </button>
            </>
          ) : null}
          {menuNode?.type === 'hitl' ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => onConfigureHitl(menu.nodeId as FlowGraphNodeId)}
              className="rounded-xl px-3 py-2 text-left text-sm font-medium text-rose-800 hover:bg-rose-50"
            >
              Configure HITL
            </button>
          ) : null}
          {menuNode?.type === 'execution_action' ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => onConfigureAction(menu.nodeId as FlowGraphNodeId)}
              className="rounded-xl px-3 py-2 text-left text-sm font-medium text-violet-800 hover:bg-violet-50"
            >
              Configure Action
            </button>
          ) : null}
          <button
            type="button"
            role="menuitem"
            onClick={() => onRemoveNode(menu.nodeId as FlowGraphNodeId)}
            className="rounded-xl px-3 py-2 text-left text-sm font-medium text-rose-700 hover:bg-rose-50"
          >
            Remove Node
          </button>
        </>
      ) : (
        <>
          {CORE_NODE_KINDS.filter((kind) => kind !== 'crew').map((kind) => (
            <button
              key={kind}
              type="button"
              role="menuitem"
              onClick={() => onAddNode(kind)}
              className="rounded-xl px-3 py-2 text-left text-sm font-medium text-stone-700 hover:bg-stone-100"
            >
              Add {nodeLabel(kind)}
            </button>
          ))}
          <div className="my-1 border-t border-stone-100" />
          <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-400">Add published crew</p>
          {publishedCrews.length > 0 ? (
            publishedCrews.map((crew) => (
              <button
                key={crew.versionId}
                type="button"
                role="menuitem"
                onClick={() => onAddCrew(crew)}
                className="rounded px-3 py-2 text-left text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
              >
                {crew.name}
              </button>
            ))
          ) : (
            <p className="px-3 py-2 text-sm text-stone-500">Publish a Crew before adding it to a Flow.</p>
          )}
          {selectedNodeId ? (
            <>
              <div className="my-1 border-t border-stone-100" />
              <button
                type="button"
                role="menuitem"
                onClick={onRemoveSelectedNode}
                className="rounded-xl px-3 py-2 text-left text-sm font-medium text-rose-700 hover:bg-rose-50"
              >
                Remove Selected Node
              </button>
            </>
          ) : null}
        </>
      )}
    </div>
  );
}
