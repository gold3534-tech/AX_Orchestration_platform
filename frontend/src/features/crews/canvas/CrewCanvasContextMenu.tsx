import type { XYPosition } from '@xyflow/react';
import type { CrewCanvasNodeId } from './crewCanvasTypes';

export type CrewCanvasMenuState = {
  screenX: number;
  screenY: number;
  flowPosition: XYPosition;
  nodeId: CrewCanvasNodeId | null;
};

type MenuAsset = {
  assetId: string;
  versionId: string;
  name: string;
};

export function CrewCanvasContextMenu({
  menu,
  availableAgents,
  availableTasks,
  onAddNode,
  onAssignAgent,
  onAssignTask,
  onDeleteNode,
}: {
  menu: CrewCanvasMenuState;
  availableAgents: MenuAsset[];
  availableTasks: MenuAsset[];
  onAddNode: (position: XYPosition) => void;
  onAssignAgent: (nodeId: CrewCanvasNodeId, agentAssetId: string) => void;
  onAssignTask: (nodeId: CrewCanvasNodeId, taskAssetId: string) => void;
  onDeleteNode: (nodeId: CrewCanvasNodeId) => void;
}) {
  return (
    <div
      className="absolute z-20 w-64 overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fff6df] shadow-[5px_5px_0_#7a5739]"
      style={{ left: menu.screenX, top: menu.screenY }}
    >
      <div className="border-b border-stone-100 px-3 py-2">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">
          {menu.nodeId ? 'Node menu' : 'Canvas menu'}
        </p>
      </div>

      {!menu.nodeId ? (
        <button
          type="button"
          onClick={() => onAddNode(menu.flowPosition)}
          className="block w-full px-3 py-2 text-left text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
        >
          Add Node
        </button>
      ) : null}

      {menu.nodeId ? (
        <div className="max-h-72 overflow-y-auto py-2">
          {availableAgents.length > 0 ? (
            <div className="px-2 py-1">
              <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-stone-400">Bind Agent</p>
              {availableAgents.map((agent) => (
                <button
                  key={agent.assetId}
                  type="button"
                  onClick={() => onAssignAgent(menu.nodeId as CrewCanvasNodeId, agent.assetId)}
                  className="mt-1 block w-full rounded px-2 py-1.5 text-left text-sm font-semibold text-stone-700 hover:bg-[#ffe6b3]"
                >
                  {agent.name}
                </button>
              ))}
            </div>
          ) : null}

          {availableTasks.length > 0 ? (
            <div className="px-2 py-1">
              <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-stone-400">Bind Task</p>
              {availableTasks.map((task) => (
                <button
                  key={task.assetId}
                  type="button"
                  onClick={() => onAssignTask(menu.nodeId as CrewCanvasNodeId, task.assetId)}
                  className="mt-1 block w-full rounded-xl px-2 py-1.5 text-left text-sm text-stone-700 hover:bg-emerald-50"
                >
                  {task.name}
                </button>
              ))}
            </div>
          ) : null}

          <button
            type="button"
            onClick={() => onDeleteNode(menu.nodeId as CrewCanvasNodeId)}
            className="mt-1 block w-full px-3 py-2 text-left text-sm font-medium text-rose-600 hover:bg-rose-50"
          >
            Delete Node
          </button>
        </div>
      ) : null}
    </div>
  );
}
