import type { components } from '../../../types/api.generated';
import type { CrewGraphDocumentV1 } from '../../../api/crewGraphs';
import type {
  CrewGraphEntities,
  CrewGraphEntity,
  CrewGraphKnowledgeEntity,
  CrewGraphToolEntity,
  VersionKnowledgeAttachmentSummary,
  VersionToolAttachmentSummary,
} from '../hooks';
import { getDefaultCrewNodePosition, getDefaultPlaceholderNodePosition } from '../crewGraphTypes';
import type {
  CrewCanvasAgentNodeDraft,
  CrewCanvasDraft,
  CrewCanvasNodeDraft,
  CrewCanvasNodeId,
  CrewCanvasNodeSize,
  CrewCanvasTaskNodeDraft,
} from './crewCanvasTypes';
import { getOrderedTaskNodeIds } from './crewCanvasValidation';

type AssetResponse = components['schemas']['AssetResponse'];
type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];

export type CanvasDraftToGraphDocumentArgs = {
  crewAsset: AssetResponse;
  draft: CrewCanvasDraft;
  agentAssetsById: Map<string, AssetResponse>;
  taskAssetsById: Map<string, AssetResponse>;
  toolCatalogByKey: Map<string, ToolCatalogResponse>;
  agentVersionTools?: Map<string, string[]>;
  taskVersionTools?: Map<string, string[]>;
  agentVersionToolAttachments?: Map<string, VersionToolAttachmentSummary[]>;
  agentVersionKnowledgeAttachments?: Map<string, VersionKnowledgeAttachmentSummary[]>;
  taskVersionToolAttachments?: Map<string, VersionToolAttachmentSummary[]>;
};

export function canvasDraftToGraphDocument({
  crewAsset,
  draft,
  agentAssetsById,
  taskAssetsById,
  toolCatalogByKey,
  agentVersionTools = new Map<string, string[]>(),
  taskVersionTools = new Map<string, string[]>(),
  agentVersionToolAttachments = new Map<string, VersionToolAttachmentSummary[]>(),
  agentVersionKnowledgeAttachments = new Map<string, VersionKnowledgeAttachmentSummary[]>(),
  taskVersionToolAttachments = new Map<string, VersionToolAttachmentSummary[]>(),
}: CanvasDraftToGraphDocumentArgs): CrewGraphDocumentV1 & { entities: CrewGraphEntities } {
  const orderedDraftNodes = getDraftNodesInStableOrder(draft);
  const agentNodes = orderedDraftNodes.filter((node): node is CrewCanvasAgentNodeDraft => node.kind === 'agent');
  const taskNodes = orderedDraftNodes.filter((node): node is CrewCanvasTaskNodeDraft => node.kind === 'task');
  const orderedTaskNodeIds = getOrderedTaskNodeIds(draft);
  const taskNodesById = new Map(taskNodes.map((node) => [node.nodeId, node]));
  const orderedTaskNodes = orderedTaskNodeIds.map((nodeId) => taskNodesById.get(nodeId)).filter(Boolean) as CrewCanvasTaskNodeDraft[];
  const agentAssets = agentNodes.map((node) => getRequiredAsset(agentAssetsById, node.assetId, node.versionId, 'Agent'));
  const taskAssets = orderedTaskNodes.map((node) => getRequiredAsset(taskAssetsById, node.assetId, node.versionId, 'Task'));
  const agentVersionIds = new Set(agentNodes.map((node) => node.versionId));
  const taskVersionIds = new Set(taskNodes.map((node) => node.versionId));
  const toolKeys = unique([
    ...toolKeysForSelectedVersions(agentVersionTools, agentVersionIds),
    ...toolKeysForSelectedVersions(taskVersionTools, taskVersionIds),
  ]).filter((toolKey) => toolCatalogByKey.has(toolKey));
  const crewEntity = toGraphEntity(crewAsset);
  const crewNodeId = `crew:${crewAsset.id}`;
  const nodeIndexForLane = createLaneIndexCounter();
  const crewNodeSize = validNodeSize((draft.nodeSizes ?? {})[crewNodeId]);

  const nodes = [
    {
      id: crewNodeId,
      type: 'crew',
      position: draft.nodePositions[crewNodeId] ?? { x: 32, y: 32 },
      ...(crewNodeSize ? { style: crewNodeSize } : {}),
      data: {
        assetId: crewAsset.id,
        versionId: crewAsset.current_version.id,
        processType: asString(crewEntity.payload.process ?? crewEntity.payload.process_type) || undefined,
      },
    },
    ...orderedDraftNodes.map((node) => canvasNodeToGraphNode(node, nodeIndexForLane(node), draft.nodePositions, crewNodeId)),
  ] as CrewGraphDocumentV1['nodes'];

  const directEdges = draft.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: edge.kind,
  }));
  const edges = directEdges as CrewGraphDocumentV1['edges'];

  const entities: CrewGraphEntities = {
    agents: Object.fromEntries(agentAssets.map((asset) => [asset.current_version.id, toGraphEntity(asset)])),
    tasks: Object.fromEntries(taskAssets.map((asset) => [asset.current_version.id, toGraphEntity(asset)])),
    crews: {
      [crewAsset.current_version.id]: crewEntity,
    },
    tools: Object.fromEntries(
      toolKeys.map((toolKey) => {
        const tool = toolCatalogByKey.get(toolKey);
        return [
          toolKey,
          {
            tool_key: toolKey,
            name: tool?.name ?? toolKey,
            description: tool?.description ?? '',
            tool_type: tool?.tool_type ?? 'local',
            module_path: tool?.module_path ?? '',
            class_name: tool?.class_name ?? '',
            default_config_json: asPayloadRecord(tool?.default_config_json),
            config_schema_json: asPayloadRecord(tool?.config_schema_json),
            input_schema_json: asPayloadRecord(tool?.input_schema_json),
            ui_schema_json: asPayloadRecord(tool?.ui_schema_json),
            required_env_vars: Array.isArray(tool?.required_env_vars) ? tool.required_env_vars : [],
            credential_requirements: Array.isArray(tool?.credential_requirements) ? tool.credential_requirements : [],
            attachments: [
              ...versionToolAttachmentsFor(toolKey, agentVersionTools, agentVersionIds, agentVersionToolAttachments),
              ...versionToolAttachmentsFor(toolKey, taskVersionTools, taskVersionIds, taskVersionToolAttachments),
            ],
          } satisfies CrewGraphToolEntity,
        ];
      }),
    ),
    knowledge: knowledgeEntitiesForSelectedAgentVersions(agentVersionIds, agentVersionKnowledgeAttachments),
  };

  return {
    schemaVersion: 1,
    layoutDirection: null,
    viewport: null,
    nodes,
    edges,
    entities,
  };
}

function canvasNodeToGraphNode(
  node: CrewCanvasNodeDraft,
  index: number,
  nodePositions: CrewCanvasDraft['nodePositions'],
  parentId: string,
): CrewGraphDocumentV1['nodes'][number] {
  if (node.kind === 'placeholder') {
    return {
      id: node.nodeId,
      type: 'placeholder',
      position: nodePositions[node.nodeId] ?? getDefaultPlaceholderNodePosition(index),
      parentId,
      extent: 'parent',
      data: { kind: 'placeholder' },
    };
  }

  if (node.kind === 'agent') {
    return {
      id: node.nodeId,
      type: 'agent',
      position: nodePositions[node.nodeId] ?? getDefaultCrewNodePosition(index, 'agent'),
      parentId,
      extent: 'parent',
      data: { assetId: node.assetId, versionId: node.versionId },
    };
  }

  return {
    id: node.nodeId,
    type: 'task',
    position: nodePositions[node.nodeId] ?? getDefaultCrewNodePosition(index, 'task'),
    parentId,
    extent: 'parent',
    data: { assetId: node.assetId, versionId: node.versionId },
  };
}

function getDraftNodesInStableOrder(draft: CrewCanvasDraft) {
  const insertionIndexByNodeId = new Map<CrewCanvasNodeId, number>();
  draft.insertionOrder.forEach((nodeId, index) => {
    insertionIndexByNodeId.set(nodeId, index);
  });

  return draft.nodes
    .slice()
    .sort((left, right) => getInsertionIndex(left, insertionIndexByNodeId) - getInsertionIndex(right, insertionIndexByNodeId));
}

function getInsertionIndex(node: CrewCanvasNodeDraft, insertionIndexByNodeId: Map<CrewCanvasNodeId, number>) {
  return insertionIndexByNodeId.get(node.nodeId) ?? node.insertedAt;
}

function getRequiredAsset(assetsById: Map<string, AssetResponse>, assetId: string, versionId: string, label: 'Agent' | 'Task') {
  const asset = assetsById.get(assetId);
  if (!asset) {
    throw new Error(`${label} node references an unknown asset: ${assetId}`);
  }
  if (asset.current_version.id !== versionId) {
    throw new Error(
      `${label} node references version ${versionId}, but asset ${assetId} current version is ${asset.current_version.id}. Refresh the canvas and rebind the node.`,
    );
  }
  return asset;
}

function createLaneIndexCounter() {
  const counts = {
    placeholder: 0,
    agent: 0,
    task: 0,
  };

  return (node: CrewCanvasNodeDraft) => {
    const index = counts[node.kind];
    counts[node.kind] += 1;
    return index;
  };
}

function validNodeSize(size: CrewCanvasNodeSize | undefined): CrewCanvasNodeSize | null {
  if (!size) return null;
  if (!Number.isFinite(size.width) || !Number.isFinite(size.height) || size.width <= 0 || size.height <= 0) return null;
  return size;
}

function toGraphEntity(asset: AssetResponse): CrewGraphEntity {
  return {
    asset_id: asset.id,
    version_id: asset.current_version.id,
    version_no: asset.current_version.version_no,
    name: asset.name,
    description: asset.description,
    status: asset.current_version.status,
    payload: asPayloadRecord(asset.current_version.payload),
  };
}

function versionToolAttachmentsFor(
  toolKey: string,
  versionTools: Map<string, string[]>,
  selectedVersionIds: Set<string>,
  versionToolAttachments: Map<string, VersionToolAttachmentSummary[]> = new Map(),
): CrewGraphToolEntity['attachments'] {
  return Array.from(versionTools.entries())
    .filter(([versionId, versionToolKeys]) => selectedVersionIds.has(versionId) && versionToolKeys.includes(toolKey))
    .map(([versionId, versionToolKeys]) => {
      const savedAttachment = versionToolAttachments.get(versionId)?.find((attachment) => attachment.tool_key === toolKey);
      return {
        version_id: versionId,
        tool_config_json: asPayloadRecord(savedAttachment?.tool_config_json),
        sort_order: savedAttachment?.sort_order ?? versionToolKeys.indexOf(toolKey),
      };
    });
}

function toolKeysForSelectedVersions(versionTools: Map<string, string[]>, selectedVersionIds: Set<string>) {
  return Array.from(versionTools.entries())
    .filter(([versionId]) => selectedVersionIds.has(versionId))
    .flatMap(([, versionToolKeys]) => versionToolKeys);
}

function knowledgeEntitiesForSelectedAgentVersions(
  selectedVersionIds: Set<string>,
  agentVersionKnowledgeAttachments: Map<string, VersionKnowledgeAttachmentSummary[]> = new Map(),
): Record<string, CrewGraphKnowledgeEntity> {
  const knowledgeById = new Map<string, CrewGraphKnowledgeEntity>();
  for (const [versionId, attachments] of agentVersionKnowledgeAttachments.entries()) {
    if (!selectedVersionIds.has(versionId)) continue;
    for (const attachment of attachments) {
      const existing = knowledgeById.get(attachment.knowledge_item_id);
      const nextAttachment = {
        version_id: versionId,
        sort_order: attachment.sort_order,
      };
      if (existing) {
        existing.attachments.push(nextAttachment);
        continue;
      }
      knowledgeById.set(attachment.knowledge_item_id, {
        id: attachment.knowledge_item_id,
        name: attachment.knowledge.name,
        status: attachment.knowledge.status,
        attachments: [nextAttachment],
      });
    }
  }
  return Object.fromEntries(knowledgeById);
}

function unique<T>(values: T[]) {
  return Array.from(new Set(values));
}

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function asPayloadRecord(value: unknown) {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}
