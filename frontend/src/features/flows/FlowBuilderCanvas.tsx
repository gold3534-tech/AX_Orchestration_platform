import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  ConnectionMode,
  Controls,
  ReactFlow,
} from '@xyflow/react';
import type {
  Connection,
  Edge,
  EdgeChange,
  Node,
  NodeChange,
  ReactFlowInstance,
  XYPosition,
} from '@xyflow/react';
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { CanvasEmptyState, CanvasFrame, CanvasPanel, CanvasPanelHeader } from '../../components/canvas';
import type { FlowCanvasDraft, PublishedCrewOption } from './hooks';
import {
  defaultFlowNodePosition,
  isFlowGraphNodeId,
  type FlowBuilderNode,
  type FlowGraphNodeId,
  type FlowNodeKind,
} from './flowGraphTypes';
import {
  connectFlowCanvasNodes,
  resolveCrewVisual,
} from './canvas/flowCanvasHelpers';
import { FlowCanvasContextMenu, type FlowCanvasMenuState } from './canvas/FlowCanvasContextMenu';
import { CORE_NODE_KINDS, nodeDimensions, nodeLabel, nodeTypes } from './canvas/FlowCanvasNodes';
import { ExecutionActionInspector } from './canvas/ExecutionActionInspector';
import { HitlNodeInspector } from './canvas/HitlNodeInspector';
import { InputBindingInspector } from './canvas/InputBindingInspector';
import { missingInputsByNodeId } from './canvas/inputBindings';
import { OutputFieldsInspector } from './canvas/OutputFieldsInspector';

import '@xyflow/react/dist/style.css';

export {
  connectFlowCanvasNodes,
  getCrewFlowNodeDimensions,
  getCrewStepSummaries,
  getOutputFieldOptions,
  resolveCrewVisual,
} from './canvas/flowCanvasHelpers';
export type { CrewStepSummary, OutputFieldOption, ResolvedCrewVisual } from './canvas/flowCanvasHelpers';

type FlowBuilderCanvasProps = {
  draft: FlowCanvasDraft;
  publishedCrews: PublishedCrewOption[];
  onAddNode: (kind: FlowNodeKind, position: XYPosition) => void;
  onAddCrew: (position?: XYPosition, crew?: PublishedCrewOption) => void;
  onSelectNode: (nodeId: FlowGraphNodeId | null) => void;
  onChangeDraft: (draft: FlowCanvasDraft) => void;
  showTopAddCrew?: boolean;
};

type CanvasNode = FlowBuilderNode;
type CanvasEdge = Edge<{ kind?: 'flow' | 'route' | 'tool_reference'; route?: string }>;

const DEFAULT_MENU_POSITION: XYPosition = { x: 240, y: 180 };
export const FLOW_EDGE_STYLE = { stroke: '#7a5739', strokeWidth: 3 };
const edgeTypes = {};

function defaultNodeData(
  kind: FlowNodeKind,
  data: Record<string, unknown>,
  publishedCrews: PublishedCrewOption[],
  draft: FlowCanvasDraft,
) {
  const versionId = typeof data.versionId === 'string' ? data.versionId : '';
  const selectedCrew = kind === 'crew' ? resolveCrewVisual(versionId, draft, publishedCrews) : undefined;

  return {
    kind,
    label: selectedCrew?.name ?? nodeLabel(kind),
    runtimeSnapshot: selectedCrew?.runtimeSnapshot,
    ...data,
  };
}

export function FlowBuilderCanvas({
  draft,
  publishedCrews,
  onAddNode,
  onAddCrew,
  onSelectNode,
  onChangeDraft,
  showTopAddCrew = false,
}: FlowBuilderCanvasProps) {
  const [contextMenu, setContextMenu] = useState<FlowCanvasMenuState | null>(null);
  const [hitlNodeId, setHitlNodeId] = useState<FlowGraphNodeId | null>(null);
  const [actionNodeId, setActionNodeId] = useState<FlowGraphNodeId | null>(null);
  const [outputFieldNodeId, setOutputFieldNodeId] = useState<FlowGraphNodeId | null>(null);
  const [inputBindingTarget, setInputBindingTarget] = useState<{ nodeId: FlowGraphNodeId; inputName: string } | null>(null);
  const reactFlowRef = useRef<ReactFlowInstance<CanvasNode, CanvasEdge> | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const stableNodeTypes = useMemo(() => nodeTypes, []);
  const stableEdgeTypes = useMemo(() => edgeTypes, []);
  const missingInputs = useMemo(() => missingInputsByNodeId(draft, publishedCrews), [draft, publishedCrews]);
  const baseDraftNodes: CanvasNode[] = useMemo(
    () =>
      draft.nodes.map((node) => {
        const nodeData = defaultNodeData(node.type, node.data, publishedCrews, draft);
        const crewMissingInputs = node.type === 'crew' ? (missingInputs[node.id] ?? []) : [];
        const dimensions = nodeDimensions(node.type, nodeData.runtimeSnapshot);
        const readOnlyToolNode = node.type === 'tool';
        return {
          id: node.id,
          type: node.type,
          position: node.position,
          width: dimensions.width,
          height: dimensions.height,
          initialWidth: dimensions.width,
          initialHeight: dimensions.height,
          selected: readOnlyToolNode ? false : node.id === draft.selectedNodeId,
          draggable: !readOnlyToolNode,
          connectable: !readOnlyToolNode,
          selectable: !readOnlyToolNode,
          data: {
            ...nodeData,
            missingInputs: crewMissingInputs,
            onOpenInputBinding:
              node.type === 'crew'
                ? (inputName: string) => {
                    setInputBindingTarget({ nodeId: node.id, inputName });
                  }
                : undefined,
          },
        };
      }),
    [draft, draft.nodes, draft.selectedNodeId, missingInputs, publishedCrews],
  );
  const draftNodes = baseDraftNodes;
  const [nodes, setNodes] = useState<CanvasNode[]>(draftNodes);
  const hitlNode = hitlNodeId ? draft.nodes.find((node) => node.id === hitlNodeId && node.type === 'hitl') : null;
  const actionNode = actionNodeId ? draft.nodes.find((node) => node.id === actionNodeId && node.type === 'execution_action') : null;
  const outputFieldNode = outputFieldNodeId ? draft.nodes.find((node) => node.id === outputFieldNodeId && node.type === 'output') : null;
  const edges: CanvasEdge[] = useMemo(
    () =>
      draft.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: 'smoothstep',
        style: FLOW_EDGE_STYLE,
        data: { ...edge.data, kind: edge.type },
      })),
    [draft.edges],
  );

  useEffect(() => {
    setNodes(draftNodes);
  }, [draftNodes]);

  function openMenu(event: MouseEvent | ReactMouseEvent, nodeId?: FlowGraphNodeId) {
    event.preventDefault();
    const targetNodeId =
      nodeId ??
      (event.target instanceof HTMLElement
        ? event.target.closest<HTMLElement>('.react-flow__node')?.dataset.id
        : undefined);
    const menuNodeId = targetNodeId && isFlowGraphNodeId(targetNodeId) ? targetNodeId : undefined;
    const canvasRect = canvasRef.current?.getBoundingClientRect();
    const screenPosition = {
      x: canvasRect ? event.clientX - canvasRect.left : event.clientX,
      y: canvasRect ? event.clientY - canvasRect.top : event.clientY,
    };
    const flowPosition = reactFlowRef.current?.screenToFlowPosition({ x: event.clientX, y: event.clientY }) ?? {
      x: screenPosition.x,
      y: screenPosition.y,
    };

    setContextMenu({
      screenX: screenPosition.x,
      screenY: screenPosition.y,
      flowPosition,
      nodeId: menuNodeId,
    });
  }

  function closeMenu() {
    setContextMenu(null);
  }

  function getVisibleInsertPosition(kind: FlowNodeKind) {
    const basePosition = defaultFlowNodePosition(kind);
    const sameKindCount = draft.nodes.filter((node) => node.type === kind).length;
    const stagger = sameKindCount * 36;

    return {
      x: basePosition.x + stagger,
      y: basePosition.y + stagger,
    };
  }

  function updateNodes(changes: NodeChange<CanvasNode>[]) {
    setNodes((currentNodes) => applyNodeChanges(changes, currentNodes) as CanvasNode[]);

    const removedNodeIds = changes
      .filter((change): change is Extract<NodeChange<CanvasNode>, { type: 'remove' }> => change.type === 'remove')
      .map((change) => change.id as FlowGraphNodeId);
    const draftNodeIds = new Set(draft.nodes.map((node) => node.id));
    const removedDraftNodeIds = removedNodeIds.filter((nodeId) => draftNodeIds.has(nodeId));

    if (removedDraftNodeIds.length > 0) {
      const removedNodeIdSet = new Set(removedDraftNodeIds);
      onChangeDraft({
        ...draft,
        selectedNodeId: draft.selectedNodeId && removedNodeIdSet.has(draft.selectedNodeId) ? null : draft.selectedNodeId,
        nodes: draft.nodes.filter((node) => !removedNodeIdSet.has(node.id)),
        edges: draft.edges.filter((edge) => !removedNodeIdSet.has(edge.source) && !removedNodeIdSet.has(edge.target)),
      });
    }
  }

  function updateEdges(changes: EdgeChange<CanvasEdge>[]) {
    const nextEdges = applyEdgeChanges(changes, edges);
    const nextEdgeIds = new Set(nextEdges.map((edge) => edge.id));

    onChangeDraft({
      ...draft,
      edges: draft.edges.filter((edge) => nextEdgeIds.has(edge.id)),
    });
  }

  function connectNodes(connection: Connection) {
    const nextDraft = connectFlowCanvasNodes(draft, connection);

    if (nextDraft !== draft) {
      onChangeDraft(nextDraft);
    }
  }

  function removeNode(nodeId: FlowGraphNodeId) {
    onChangeDraft({
      ...draft,
      selectedNodeId: draft.selectedNodeId === nodeId ? null : draft.selectedNodeId,
      nodes: draft.nodes.filter((node) => node.id !== nodeId),
      edges: draft.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    });
  }

  function removeSelectedNode() {
    if (draft.selectedNodeId) {
      removeNode(draft.selectedNodeId);
    }
  }

  function addFromMenu(kind: FlowNodeKind) {
    const position = contextMenu?.flowPosition ?? DEFAULT_MENU_POSITION;

    if (kind === 'crew') {
      if (publishedCrews.length === 1) {
        closeMenu();
        onAddCrew(position, publishedCrews[0]);
      }
      return;
    }

    closeMenu();
    onAddNode(kind, position);
  }

  function addFromToolbar(kind: FlowNodeKind) {
    closeMenu();
    const position = getVisibleInsertPosition(kind);

    if (kind === 'crew') {
      if (publishedCrews.length === 1) {
        onAddCrew(position, publishedCrews[0]);
      } else if (publishedCrews.length > 1) {
        setContextMenu({
          screenX: 12,
          screenY: 52,
          flowPosition: position,
        });
      }
      return;
    }

    onAddNode(kind, position);
  }

  const toolbarNodeKinds = showTopAddCrew ? CORE_NODE_KINDS.filter((kind) => kind !== 'crew') : CORE_NODE_KINDS;

  return (
    <CanvasPanel>
      <CanvasPanelHeader
        eyebrow="Flow builder"
        title="Canvas"
        description={
          <>
            Right-click to add or remove nodes. Drag handles to connect. {publishedCrews.length} published crew
            {publishedCrews.length === 1 ? '' : 's'} available.
          </>
        }
        actionsLabel="Flow node creation toolbar"
        actions={
          <>
            {toolbarNodeKinds.map((kind) => (
              <button
                key={kind}
                type="button"
                onClick={() => addFromToolbar(kind)}
                disabled={kind === 'crew' && publishedCrews.length === 0}
                className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-1.5 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3] disabled:cursor-not-allowed disabled:opacity-50"
              >
                Add {nodeLabel(kind)}
              </button>
            ))}

            {showTopAddCrew ? (
              <button
                type="button"
                onClick={() => addFromToolbar('crew')}
                disabled={publishedCrews.length === 0}
                className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa]"
              >
                Add Crew
              </button>
            ) : null}
          </>
        }
      />

      <CanvasFrame
        ref={canvasRef}
        aria-label="Flow canvas"
        onContextMenu={(event) => openMenu(event)}
      >
        <ReactFlow<CanvasNode, CanvasEdge>
          nodes={nodes}
          edges={edges}
          nodeTypes={stableNodeTypes}
          edgeTypes={stableEdgeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          nodesDraggable
          nodesConnectable
          elementsSelectable
          connectionMode={ConnectionMode.Loose}
          connectionRadius={40}
          onInit={(instance) => {
            reactFlowRef.current = instance;
          }}
          onNodesChange={updateNodes}
          onNodeDragStop={(_event, node) => {
            if (node.type === 'tool') {
              return;
            }

            onChangeDraft({
              ...draft,
              nodes: draft.nodes.map((draftNode) =>
                draftNode.id === node.id ? { ...draftNode, position: node.position } : draftNode,
              ),
            });
          }}
          onEdgesChange={updateEdges}
          onConnect={connectNodes}
          onNodeClick={(_event, node) => {
            closeMenu();
            onSelectNode(node.type === 'tool' ? null : node.id);
          }}
          onNodeContextMenu={(event, node) => {
            if (node.type === 'tool') {
              event.preventDefault();
              closeMenu();
              onSelectNode(null);
              return;
            }

            onSelectNode(node.id);
            openMenu(event, node.id);
          }}
          onPaneClick={() => {
            closeMenu();
            onSelectNode(null);
          }}
          onPaneContextMenu={(event) => openMenu(event)}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <Background
            variant={BackgroundVariant.Dots} // 패턴을 '선'에서 '점'으로 변경
            gap={18}                         // 점 사이의 간격 (숫자가 작을수록 촘촘함)
            size={3}                         // 점의 크기
            lineWidth={1}                    // (일부 버전 대응) 점의 두께
            color="#b98957"                  // 점의 색상
            bgColor="#f8e8c8"                // 전체 배경색
          />
          <Controls position="bottom-right" showInteractive={false} />
        </ReactFlow>

        {draft.nodes.length === 0 ? (
          <CanvasEmptyState
            eyebrow="Start building"
            title="Right-click the canvas to add nodes"
            textAlign="center"
          >
            Add Input, Start, Crew, Router, HITL, and Output blocks, then connect them into a runtime-ready Flow.
          </CanvasEmptyState>
        ) : null}

        {contextMenu ? (
          <FlowCanvasContextMenu
            menu={contextMenu}
            nodes={draft.nodes}
            selectedNodeId={draft.selectedNodeId}
            publishedCrews={publishedCrews}
            onAddNode={addFromMenu}
            onAddCrew={(crew) => {
              onAddCrew(contextMenu.flowPosition, crew);
              closeMenu();
            }}
            onConfigureHitl={(nodeId) => {
              setHitlNodeId(nodeId);
              closeMenu();
            }}
            onConfigureAction={(nodeId) => {
              setActionNodeId(nodeId);
              closeMenu();
            }}
            onSelectOutputFields={(nodeId) => {
              setOutputFieldNodeId(nodeId);
              closeMenu();
            }}
            onClearOutputFields={(nodeId) => {
              onChangeDraft({
                ...draft,
                nodes: draft.nodes.map((node) =>
                  node.id === nodeId ? { ...node, data: { ...node.data, fields: [] } } : node,
                ),
              });
              closeMenu();
            }}
            onRemoveNode={(nodeId) => {
              removeNode(nodeId);
              closeMenu();
            }}
            onRemoveSelectedNode={() => {
              removeSelectedNode();
              closeMenu();
            }}
          />
        ) : null}
      </CanvasFrame>
      {hitlNode ? (
        <HitlNodeInspector
          draft={draft}
          hitlNode={hitlNode}
          onChangeDraft={onChangeDraft}
          onClose={() => setHitlNodeId(null)}
        />
      ) : null}
      {actionNode ? (
        <ExecutionActionInspector
          draft={draft}
          actionNode={actionNode}
          onChangeDraft={onChangeDraft}
          onClose={() => setActionNodeId(null)}
        />
      ) : null}
      {outputFieldNode ? (
        <OutputFieldsInspector
          draft={draft}
          outputNode={outputFieldNode}
          publishedCrews={publishedCrews}
          onChangeDraft={onChangeDraft}
          onClose={() => setOutputFieldNodeId(null)}
        />
      ) : null}
      {inputBindingTarget ? (
        <InputBindingInspector
          draft={draft}
          targetNodeId={inputBindingTarget.nodeId}
          inputName={inputBindingTarget.inputName}
          publishedCrews={publishedCrews}
          onChangeDraft={onChangeDraft}
          onClose={() => setInputBindingTarget(null)}
        />
      ) : null}
    </CanvasPanel>
  );
}
