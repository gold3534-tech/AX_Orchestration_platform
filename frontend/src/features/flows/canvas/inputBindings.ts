import type {
  FlowGraphNodeId,
  FlowInputMappingDraft,
  FlowTransferInputType,
  FlowTransferTransform,
} from '../flowGraphTypes';
import type { FlowCanvasDraft, PublishedCrewOption } from '../hooks';
import { resolveCrewVisual } from './flowCanvasHelpers';

export type UnresolvedFlowInput = {
  nodeId: FlowGraphNodeId;
  crewName: string;
  inputName: string;
};

type BuildTransformInputMappingOptions = {
  sourceNodeId: FlowGraphNodeId;
  paths: string[];
  inputType: FlowTransferInputType;
  transform: FlowTransferTransform;
  maxChars?: number;
  overflow?: 'fail' | 'truncate';
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string' && item.length > 0) : [];
}

function topicInputExists(draft: FlowCanvasDraft): boolean {
  return draft.nodes.some((node) => {
    if (node.type !== 'input') {
      return false;
    }

    const fields = Array.isArray(node.data.fields) ? node.data.fields : [];
    return fields.some((field) => isRecord(field) && field.name === 'topic');
  });
}

export function getRequiredInputs(runtimeSnapshot: unknown): string[] {
  return isRecord(runtimeSnapshot) ? stringList(runtimeSnapshot.required_inputs) : [];
}

export function findUnresolvedFlowInputs(
  draft: FlowCanvasDraft,
  publishedCrews: PublishedCrewOption[],
): UnresolvedFlowInput[] {
  const hasTopicInput = topicInputExists(draft);
  const unresolvedInputs: UnresolvedFlowInput[] = [];

  for (const node of draft.nodes) {
    if (node.type !== 'crew') {
      continue;
    }

    const versionId = typeof node.data.versionId === 'string' ? node.data.versionId : '';
    const crew = resolveCrewVisual(versionId, draft, publishedCrews);
    const requiredInputs = getRequiredInputs(crew?.runtimeSnapshot);
    const inputMappings = isRecord(node.data.inputMappings) ? node.data.inputMappings : {};
    const crewName = crew?.name || (typeof node.data.label === 'string' ? node.data.label : node.id);

    for (const inputName of requiredInputs) {
      if (inputName === 'topic' && hasTopicInput) {
        continue;
      }

      if (!isRecord(inputMappings[inputName])) {
        unresolvedInputs.push({
          nodeId: node.id,
          crewName,
          inputName,
        });
      }
    }
  }

  return unresolvedInputs;
}

export function missingInputsByNodeId(
  draft: FlowCanvasDraft,
  publishedCrews: PublishedCrewOption[],
): Partial<Record<FlowGraphNodeId, string[]>> {
  return findUnresolvedFlowInputs(draft, publishedCrews).reduce<Partial<Record<FlowGraphNodeId, string[]>>>((accumulator, input) => {
    accumulator[input.nodeId] = [...(accumulator[input.nodeId] ?? []), input.inputName];
    return accumulator;
  }, {});
}

export function formatUnresolvedFlowInputs(unresolvedInputs: UnresolvedFlowInput[]): string {
  return unresolvedInputs.map((input) => `${input.crewName}.${input.inputName}`).join('\n');
}

export function buildTransformInputMapping({
  sourceNodeId,
  paths,
  inputType,
  transform,
  maxChars = 8000,
  overflow = 'fail',
}: BuildTransformInputMappingOptions): FlowInputMappingDraft {
  return {
    source: 'transform',
    nodeId: sourceNodeId,
    paths: [...paths],
    inputType,
    transform,
    maxChars,
    overflow,
  };
}
