import {
  applyNodeChanges,
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
} from '@xyflow/react';
import type { Connection, Dimensions, EdgeChange, NodeChange, ReactFlowInstance, XYPosition } from '@xyflow/react';
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { CanvasEmptyState, CanvasFrame, CanvasPanel, CanvasPanelHeader } from '../../components/canvas';
import { ActionButton } from '../../components/shared/ActionButton';
import {
  AGENT_ASSIGNMENT_SOURCE_HANDLE,
  AGENT_ASSIGNMENT_TARGET_HANDLE,
  AgentNode,
  CrewContainerNode,
  PlaceholderNode,
  TASK_CONTEXT_SOURCE_HANDLE,
  TASK_CONTEXT_TARGET_HANDLE,
  TASK_SEQUENCE_SOURCE_HANDLE,
  TASK_SEQUENCE_TARGET_HANDLE,
  TaskNode,
} from './canvas/CrewCanvasNodes';
import { CrewCanvasContextMenu, type CrewCanvasMenuState } from './canvas/CrewCanvasContextMenu';
import { CrewCanvasLegend } from './canvas/CrewCanvasLegend';
import type { CrewCanvasEdgeKind, CrewCanvasNodeId } from './canvas/crewCanvasTypes';
import type {
  CrewGraph,
  CrewGraphEdge,
  CrewGraphNode,
  CrewGraphNodeData,
  CrewGraphNodeId,
} from './crewGraphTypes';

import '@xyflow/react/dist/style.css';

type CrewBuilderCanvasProps = {
  graph: CrewGraph;
  selectedNodeId: CrewGraphNodeId | null;
  onSelectNode: (nodeId: CrewGraphNodeId | null) => void;
  onAddFirstNode: () => void;
  onDraftSave?: () => void;
  onTestValidation?: () => void;
  onPublish?: () => void;
  onNodesChange?: (changes: NodeChange<CrewGraphNode>[]) => void;
  onNodePositionCommit?: (nodeId: CrewGraphNodeId, position: XYPosition) => void;
  onNodeSizeCommit?: (nodeId: CrewGraphNodeId, size: Dimensions) => void;
  onAutoLayout?: () => void;
  availableAgents?: Array<{ assetId: string; versionId: string; name: string }>;
  availableTasks?: Array<{ assetId: string; versionId: string; name: string }>;
  onAddNode?: (position?: XYPosition) => void;
  onAssignAgent?: (nodeId: CrewCanvasNodeId, agentAssetId: string) => void;
  onAssignTask?: (nodeId: CrewCanvasNodeId, taskAssetId: string) => void;
  onDeleteNode?: (nodeId: CrewCanvasNodeId) => void;
  onDeleteEdge?: (edgeId: string) => void;
  onConnectEdge?: (edge: { kind: CrewCanvasEdgeKind; source: CrewCanvasNodeId; target: CrewCanvasNodeId }) => void;
  isDraftSaving?: boolean;
  isValidating?: boolean;
  isPublishing?: boolean;
  draftSaveDisabled?: boolean;
  testValidationDisabled?: boolean;
  publishDisabled?: boolean;
  publishDisabledReason?: string;
  testValidationDisabledReason?: string;
};

const CREW_CONTAINER_POSITION = { x: 32, y: 32 };

const nodeTypes = {
  crew: CrewContainerNode,
  placeholder: PlaceholderNode,
  agent: AgentNode,
  task: TaskNode,
};
const edgeTypes = {};

function isEditableMenuNode(nodeId: CrewGraphNodeId | null): nodeId is CrewCanvasNodeId {
  return typeof nodeId === 'string' && (nodeId.startsWith('placeholder:') || nodeId.startsWith('agent:') || nodeId.startsWith('task:'));
}

function isCrewContainerNode(nodeId: string, nodes: CrewGraphNode[]) {
  return nodes.some((node) => node.id === nodeId && node.type === 'crew');
}

function toChildPosition(position: XYPosition) {
  return {
    x: Math.max(24, position.x - CREW_CONTAINER_POSITION.x),
    y: Math.max(56, position.y - CREW_CONTAINER_POSITION.y),
  };
}

function isValidDimensions(dimensions: Dimensions | undefined): dimensions is Dimensions {
  return Boolean(
    dimensions &&
      Number.isFinite(dimensions.width) &&
      Number.isFinite(dimensions.height) &&
      dimensions.width > 0 &&
      dimensions.height > 0,
  );
}

type CrewCanvasConnectionLike = {
  source?: string | null;
  target?: string | null;
  sourceHandle?: string | null;
  targetHandle?: string | null;
};

export function getCrewCanvasConnectionKind(connection: CrewCanvasConnectionLike): CrewCanvasEdgeKind | null {
  if (
    connection.sourceHandle === AGENT_ASSIGNMENT_SOURCE_HANDLE &&
    connection.targetHandle === AGENT_ASSIGNMENT_TARGET_HANDLE
  ) {
    return 'agent_assignment';
  }

  if (
    connection.sourceHandle === TASK_CONTEXT_SOURCE_HANDLE &&
    connection.targetHandle === TASK_CONTEXT_TARGET_HANDLE
  ) {
    return 'task_context';
  }

  if (
    connection.sourceHandle === TASK_SEQUENCE_SOURCE_HANDLE &&
    connection.targetHandle === TASK_SEQUENCE_TARGET_HANDLE
  ) {
    return 'task_sequence';
  }

  return null;
}

export function isCrewCanvasConnectionValid(connection: CrewCanvasConnectionLike) {
  return Boolean(connection.source && connection.target && getCrewCanvasConnectionKind(connection));
}

export function CrewBuilderCanvas({
  graph,
  selectedNodeId,
  onSelectNode,
  onAddFirstNode,
  onDraftSave,
  onTestValidation,
  onPublish,
  isDraftSaving = false,
  isValidating = false,
  isPublishing = false,
  draftSaveDisabled,
  testValidationDisabled,
  publishDisabled,
  publishDisabledReason,
  testValidationDisabledReason,
  onNodesChange,
  onNodePositionCommit,
  onNodeSizeCommit,
  onAutoLayout,
  availableAgents = [],
  availableTasks = [],
  onAddNode,
  onAssignAgent,
  onAssignTask,
  onDeleteNode,
  onDeleteEdge,
  onConnectEdge,
}: CrewBuilderCanvasProps) {
  const graphNodes = useMemo(
    () => graph.nodes.map((node) => ({ ...node, selected: node.id === selectedNodeId })),
    [graph.nodes, selectedNodeId],
  );
  const stableNodeTypes = useMemo(() => nodeTypes, []);
  const stableEdgeTypes = useMemo(() => edgeTypes, []);
  const [nodes, setNodes] = useState<CrewGraphNode[]>(graphNodes);
  const [menu, setMenu] = useState<CrewCanvasMenuState | null>(null);
  const reactFlowRef = useRef<ReactFlowInstance<CrewGraphNode, CrewGraphEdge> | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setNodes(graphNodes);
  }, [graphNodes]);

  const draftDisabled = draftSaveDisabled ?? !onDraftSave;
  const validationDisabled = testValidationDisabled ?? !onTestValidation;
  const publishDisabledEffective = publishDisabled ?? !onPublish;
  const busy = isDraftSaving || isValidating || isPublishing;
  const actionsWired = Boolean(onDraftSave || onTestValidation || onPublish);
  const contextNodeId = isEditableMenuNode(menu?.nodeId ?? null) ? menu?.nodeId ?? null : null;
  const boundAgentIds = useMemo(
    () =>
      new Set(
        graph.nodes.flatMap((node) => (node.data.kind === 'agent' ? [node.data.assetId] : [])),
      ),
    [graph.nodes],
  );
  const boundTaskIds = useMemo(
    () =>
      new Set(
        graph.nodes.flatMap((node) => (node.data.kind === 'task' ? [node.data.assetId] : [])),
      ),
    [graph.nodes],
  );
  const contextNode = useMemo(
    () => (contextNodeId ? graph.nodes.find((node) => node.id === contextNodeId) ?? null : null),
    [contextNodeId, graph.nodes],
  );
  const availableAgentsForMenu = useMemo(
    () =>
      availableAgents.filter(
        (agent) => !boundAgentIds.has(agent.assetId) || (contextNode?.data.kind === 'agent' && contextNode.data.assetId === agent.assetId),
      ),
    [availableAgents, boundAgentIds, contextNode],
  );
  const availableTasksForMenu = useMemo(
    () =>
      availableTasks.filter(
        (task) => !boundTaskIds.has(task.assetId) || (contextNode?.data.kind === 'task' && contextNode.data.assetId === task.assetId),
      ),
    [availableTasks, boundTaskIds, contextNode],
  );
  const hasContextActions =
    (!menu?.nodeId && Boolean(onAddNode)) ||
    (Boolean(contextNodeId) && (Boolean(onAssignAgent) || Boolean(onAssignTask) || Boolean(onDeleteNode)));

  function openMenu(event: MouseEvent | ReactMouseEvent, nodeId: CrewGraphNodeId | null) {
    event.preventDefault();
    const flowPosition = reactFlowRef.current?.screenToFlowPosition({ x: event.clientX, y: event.clientY }) ?? {
      x: event.clientX,
      y: event.clientY,
    };
    const canvasRect = canvasRef.current?.getBoundingClientRect();
    setMenu({
      screenX: canvasRect ? Math.min(Math.max(12, event.clientX - canvasRect.left), Math.max(12, canvasRect.width - 280)) : event.clientX,
      screenY: canvasRect ? Math.min(Math.max(12, event.clientY - canvasRect.top), Math.max(12, canvasRect.height - 320)) : event.clientY,
      flowPosition,
      nodeId: isEditableMenuNode(nodeId) ? nodeId : null,
    });
  }

  function closeMenu() {
    setMenu(null);
  }

  function handleNodesChange(changes: NodeChange<CrewGraphNode>[]) {
    setNodes((currentNodes) => applyNodeChanges(changes, currentNodes) as CrewGraphNode[]);

    const forwardedChanges = changes.filter((change) => change.type !== 'position' && change.type !== 'dimensions');
    if (forwardedChanges.length > 0) {
      onNodesChange?.(forwardedChanges);
    }

    for (const change of changes) {
      if (
        change.type === 'dimensions' &&
        change.resizing === false &&
        isCrewContainerNode(change.id, graph.nodes) &&
        isValidDimensions(change.dimensions)
      ) {
        onNodeSizeCommit?.(change.id as CrewGraphNodeId, change.dimensions);
      }
    }
  }

  function handleConnect(connection: Connection) {
    const kind = getCrewCanvasConnectionKind(connection);
    if (!isCrewCanvasConnectionValid(connection) || !kind || !connection.source || !connection.target) return;
    onConnectEdge?.({
      kind,
      source: connection.source as CrewCanvasNodeId,
      target: connection.target as CrewCanvasNodeId,
    });
  }

  function handleEdgesChange(changes: EdgeChange<CrewGraphEdge>[]) {
    for (const change of changes) {
      if (change.type === 'remove') {
        onDeleteEdge?.(change.id);
      }
    }
  }

  return (
    <CanvasPanel>
      <CanvasPanelHeader
        eyebrow="Crew builder"
        title="Graph draft"
        headingLevel={3}
        description={
          actionsWired
            ? 'Add nodes, bind them to existing assets, and connect runtime relationships on the canvas.'
            : 'Canvas actions are available once a crew draft is selected.'
        }
        actions={
          <>
            <button
              type="button"
              onClick={() => onAddNode?.()}
              disabled={!onAddNode}
              className="pixel-button bg-[#2f9b96] px-3 py-1.5 text-sm font-bold text-white hover:bg-[#3fb0aa] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Add Node
            </button>
            <button
              type="button"
              onClick={onAutoLayout}
              disabled={!onAutoLayout || graph.nodes.length === 0}
              className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-1.5 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Auto Align
            </button>
            <ActionButton
              variant="soft"
              onClick={onDraftSave}
              disabled={draftDisabled || busy}
              title={draftDisabled ? 'Select a crew draft to save.' : undefined}
              isPending={isDraftSaving}
              pendingLabel="Saving..."
              className="px-3 py-1.5"
            >
              Draft Save
            </ActionButton>
            <ActionButton
              variant="secondary"
              onClick={onTestValidation}
              disabled={validationDisabled || busy}
              title={validationDisabled && testValidationDisabledReason ? testValidationDisabledReason : undefined}
              isPending={isValidating}
              pendingLabel="Validating..."
              className="px-3 py-1.5"
            >
              Test Validation
            </ActionButton>
            <ActionButton
              variant="primary"
              onClick={onPublish}
              disabled={publishDisabledEffective || busy}
              title={publishDisabledEffective && publishDisabledReason ? publishDisabledReason : undefined}
              isPending={isPublishing}
              pendingLabel="Publishing..."
              className="px-3 py-1.5"
            >
              Publish
            </ActionButton>
          </>
        }
      />

      {!onDraftSave && !onPublish ? (
        <p className="mb-2 text-sm text-stone-500">Actions are present but disabled until draft/validation/publish wiring lands.</p>
      ) : publishDisabledEffective && publishDisabledReason ? (
        <p className="mb-2 text-sm text-stone-500">{publishDisabledReason}</p>
      ) : (
        <div className="mb-2" />
      )}

      <CanvasFrame ref={canvasRef} data-testid="crew-builder-canvas">
        {graph.nodes.length === 0 ? (
          <CanvasEmptyState
            eyebrow="Next canvas node"
            title="Add your first node"
            headingLevel={4}
            interactive
            action={
              <button
                type="button"
                onClick={() => onAddNode?.() ?? onAddFirstNode()}
                className="pixel-button mt-4 inline-flex items-center justify-center bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa]"
              >
                Add Node
              </button>
            }
          >
            Start with a placeholder, then bind it to an existing Agent or Task.
          </CanvasEmptyState>
        ) : null}

        <ReactFlow<CrewGraphNode, CrewGraphEdge>
          nodes={nodes}
          edges={graph.edges}
          nodeTypes={stableNodeTypes}
          edgeTypes={stableEdgeTypes}
          nodesDraggable
          nodesConnectable
          elementsSelectable
          fitView
          fitViewOptions={{ padding: 0.12 }}
          onInit={(instance) => {
            reactFlowRef.current = instance;
          }}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          isValidConnection={isCrewCanvasConnectionValid}
          onConnect={handleConnect}
          onNodeDragStop={(_, node) => {
            onNodePositionCommit?.(node.id as CrewGraphNodeId, node.position);
          }}
          onNodeClick={(event, node) => {
            const data = node.data as CrewGraphNodeData;
            if (data?.kind) onSelectNode(node.id as CrewGraphNodeId);
          }}
          onNodeContextMenu={(event, node) => openMenu(event, node.id as CrewGraphNodeId)}
          onPaneContextMenu={(event) => openMenu(event, null)}
          onPaneClick={() => {
            closeMenu();
            onSelectNode(null);
          }}
        >
          <CrewCanvasLegend />
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

        {menu && hasContextActions ? (
          <CrewCanvasContextMenu
            menu={menu}
            availableAgents={availableAgentsForMenu}
            availableTasks={availableTasksForMenu}
            onAddNode={(position) => {
              onAddNode?.(toChildPosition(position));
              closeMenu();
            }}
            onAssignAgent={(nodeId, agentAssetId) => {
              onAssignAgent?.(nodeId, agentAssetId);
              closeMenu();
            }}
            onAssignTask={(nodeId, taskAssetId) => {
              onAssignTask?.(nodeId, taskAssetId);
              closeMenu();
            }}
            onDeleteNode={(nodeId) => {
              onDeleteNode?.(nodeId);
              closeMenu();
            }}
          />
        ) : null}
      </CanvasFrame>
    </CanvasPanel>
  );
}
