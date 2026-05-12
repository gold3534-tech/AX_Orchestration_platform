import type {
  CrewCanvasAction,
  CrewCanvasDraft,
  CrewCanvasEdgeDraft,
  CrewCanvasNodeDraft,
  CrewCanvasNodeId,
  CrewCanvasProcess,
  CrewCanvasTaskNodeId,
  CrewCanvasValidationError,
} from './crewCanvasTypes';

type CrewCanvasValidationOptions = {
  process: CrewCanvasProcess;
  action: CrewCanvasAction;
};

type SequenceIndexes = {
  incomingByTaskId: Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>;
  outgoingByTaskId: Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>;
};

export function getOrderedTaskNodeIds(draft: CrewCanvasDraft): CrewCanvasTaskNodeId[] {
  const taskNodeIds = getTaskNodesByInsertion(draft).map((node) => node.nodeId);
  const taskNodeIdSet = new Set<CrewCanvasNodeId>(taskNodeIds);
  const sequenceEdges = draft.edges.filter(
    (edge) => edge.kind === 'task_sequence' && taskNodeIdSet.has(edge.source) && taskNodeIdSet.has(edge.target) && edge.source !== edge.target,
  );
  const { incomingByTaskId, outgoingByTaskId } = getSequenceIndexes(sequenceEdges);
  const orderedTaskNodeIds: CrewCanvasTaskNodeId[] = [];
  const visitedTaskNodeIds = new Set<CrewCanvasTaskNodeId>();

  const chainHeads = taskNodeIds.filter((taskNodeId) => outgoingByTaskId.has(taskNodeId) && !incomingByTaskId.has(taskNodeId));
  for (const chainHead of chainHeads) {
    let currentTaskNodeId: CrewCanvasTaskNodeId | undefined = chainHead;
    const chainVisitedTaskNodeIds = new Set<CrewCanvasTaskNodeId>();

    while (currentTaskNodeId && !visitedTaskNodeIds.has(currentTaskNodeId) && !chainVisitedTaskNodeIds.has(currentTaskNodeId)) {
      orderedTaskNodeIds.push(currentTaskNodeId);
      visitedTaskNodeIds.add(currentTaskNodeId);
      chainVisitedTaskNodeIds.add(currentTaskNodeId);

      const nextEdges: CrewCanvasEdgeDraft[] = outgoingByTaskId.get(currentTaskNodeId) ?? [];
      currentTaskNodeId = isTaskNodeId(nextEdges[0]?.target) ? nextEdges[0].target : undefined;
    }
  }

  for (const taskNodeId of taskNodeIds) {
    if (!visitedTaskNodeIds.has(taskNodeId)) orderedTaskNodeIds.push(taskNodeId);
  }

  return orderedTaskNodeIds;
}

export function getCrewCanvasValidation(draft: CrewCanvasDraft, options: CrewCanvasValidationOptions) {
  const errors: CrewCanvasValidationError[] = [];
  const orderedTaskNodeIds = getOrderedTaskNodeIds(draft);
  const taskNodeIds = getTaskNodesByInsertion(draft).map((node) => node.nodeId);
  const taskNodeIdSet = new Set<CrewCanvasNodeId>(taskNodeIds);
  const agentNodeIdSet = new Set<CrewCanvasNodeId>(draft.nodes.filter((node) => node.kind === 'agent').map((node) => node.nodeId));

  if (taskNodeIds.length === 0 && options.action !== 'save') {
    errors.push({
      code: 'missing_task',
      message: 'Crew canvas must include at least one task before validation or publish.',
    });
  }

  validatePlaceholders(draft, options, errors);
  validateAgentAssignments(draft, options, taskNodeIds, taskNodeIdSet, agentNodeIdSet, errors);
  validateTaskSequences(draft, taskNodeIdSet, errors);
  validateTaskContexts(draft, orderedTaskNodeIds, taskNodeIdSet, errors);

  return {
    isValid: errors.length === 0,
    errors,
    orderedTaskNodeIds,
  };
}

function validatePlaceholders(
  draft: CrewCanvasDraft,
  options: CrewCanvasValidationOptions,
  errors: CrewCanvasValidationError[],
) {
  if (options.action === 'save') return;

  for (const node of draft.nodes) {
    if (node.kind !== 'placeholder') continue;

    errors.push({
      code: 'placeholder_unbound',
      message: 'Bind or remove placeholder nodes before validation or publish.',
      nodeId: node.nodeId,
    });
  }
}

function validateAgentAssignments(
  draft: CrewCanvasDraft,
  options: CrewCanvasValidationOptions,
  taskNodeIds: CrewCanvasTaskNodeId[],
  taskNodeIdSet: Set<CrewCanvasNodeId>,
  agentNodeIdSet: Set<CrewCanvasNodeId>,
  errors: CrewCanvasValidationError[],
) {
  const incomingAssignmentsByTaskId = new Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>();

  for (const edge of draft.edges) {
    if (edge.kind !== 'agent_assignment') continue;

    if (!agentNodeIdSet.has(edge.source) || !taskNodeIdSet.has(edge.target)) {
      errors.push({
        code: 'agent_assignment_invalid_endpoint',
        message: 'Agent assignment must connect an agent to a task.',
        edgeId: edge.id,
      });
      continue;
    }

    if (isTaskNodeId(edge.target)) {
      const assignments = incomingAssignmentsByTaskId.get(edge.target) ?? [];
      assignments.push(edge);
      incomingAssignmentsByTaskId.set(edge.target, assignments);
    }
  }

  for (const [taskNodeId, assignments] of incomingAssignmentsByTaskId) {
    if (assignments.length > 1) {
      errors.push({
        code: 'agent_assignment_multiple',
        message: 'Task can receive at most one agent assignment.',
        nodeId: taskNodeId,
      });
    }
  }

  if (options.process === 'sequential' && options.action !== 'save') {
    for (const taskNodeId of taskNodeIds) {
      if (!incomingAssignmentsByTaskId.has(taskNodeId)) {
        errors.push({
          code: 'agent_assignment_missing',
          message: 'Sequential tasks must have an assigned agent before validation or publish.',
          nodeId: taskNodeId,
        });
      }
    }
  }
}

function validateTaskContexts(
  draft: CrewCanvasDraft,
  orderedTaskNodeIds: CrewCanvasTaskNodeId[],
  taskNodeIdSet: Set<CrewCanvasNodeId>,
  errors: CrewCanvasValidationError[],
) {
  const orderIndexByTaskId = new Map(orderedTaskNodeIds.map((taskNodeId, index) => [taskNodeId, index]));

  for (const edge of draft.edges) {
    if (edge.kind !== 'task_context') continue;

    if (!taskNodeIdSet.has(edge.source) || !taskNodeIdSet.has(edge.target)) {
      errors.push({
        code: 'task_context_invalid_endpoint',
        message: 'Context edge must connect one task to another task.',
        edgeId: edge.id,
      });
      continue;
    }

    if (edge.source === edge.target) {
      errors.push({
        code: 'task_context_self',
        message: 'Task cannot use itself as context.',
        edgeId: edge.id,
      });
      continue;
    }

    if (!isTaskNodeId(edge.source) || !isTaskNodeId(edge.target)) continue;

    const sourceIndex = orderIndexByTaskId.get(edge.source);
    const targetIndex = orderIndexByTaskId.get(edge.target);
    if (sourceIndex === undefined || targetIndex === undefined) continue;

    if (sourceIndex >= targetIndex) {
      errors.push({
        code: 'task_context_order',
        message: 'Context source task must run before the dependent task.',
        edgeId: edge.id,
      });
    }
  }
}

function validateTaskSequences(draft: CrewCanvasDraft, taskNodeIdSet: Set<CrewCanvasNodeId>, errors: CrewCanvasValidationError[]) {
  const sequenceEdges: CrewCanvasEdgeDraft[] = [];

  for (const edge of draft.edges) {
    if (edge.kind !== 'task_sequence') continue;

    if (!taskNodeIdSet.has(edge.source) || !taskNodeIdSet.has(edge.target)) {
      errors.push({
        code: 'task_sequence_invalid_endpoint',
        message: 'Task sequence must connect one task to another task.',
        edgeId: edge.id,
      });
      continue;
    }

    if (edge.source === edge.target) {
      errors.push({
        code: 'task_sequence_self',
        message: 'Task cannot sequence to itself.',
        edgeId: edge.id,
      });
      continue;
    }

    sequenceEdges.push(edge);
  }

  const { incomingByTaskId, outgoingByTaskId } = getSequenceIndexes(sequenceEdges);
  for (const [taskNodeId, edges] of incomingByTaskId) {
    if (edges.length > 1) {
      errors.push({
        code: 'task_sequence_multiple_input',
        message: 'Task sequence can have at most one incoming green edge.',
        nodeId: taskNodeId,
      });
    }
  }

  for (const [taskNodeId, edges] of outgoingByTaskId) {
    if (edges.length > 1) {
      errors.push({
        code: 'task_sequence_multiple_output',
        message: 'Task sequence can have at most one outgoing green edge.',
        nodeId: taskNodeId,
      });
    }
  }

  if (hasSequenceCycle(outgoingByTaskId)) {
    errors.push({
      code: 'task_sequence_cycle',
      message: 'Task sequence cannot contain a cycle.',
    });
  }
}

function getTaskNodesByInsertion(draft: CrewCanvasDraft) {
  const insertionIndexByNodeId = new Map(draft.insertionOrder.map((nodeId, index) => [nodeId, index]));

  return draft.nodes
    .filter((node): node is Extract<CrewCanvasNodeDraft, { kind: 'task' }> => node.kind === 'task')
    .slice()
    .sort((left, right) => getInsertionIndex(left.nodeId, left.insertedAt, insertionIndexByNodeId) - getInsertionIndex(right.nodeId, right.insertedAt, insertionIndexByNodeId));
}

function getInsertionIndex(nodeId: CrewCanvasNodeId, insertedAt: number, insertionIndexByNodeId: Map<CrewCanvasNodeId, number>) {
  return insertionIndexByNodeId.get(nodeId) ?? insertedAt;
}

function getSequenceIndexes(sequenceEdges: readonly CrewCanvasEdgeDraft[]): SequenceIndexes {
  const incomingByTaskId = new Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>();
  const outgoingByTaskId = new Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>();

  for (const edge of sequenceEdges) {
    if (!isTaskNodeId(edge.source) || !isTaskNodeId(edge.target)) continue;

    const outgoingEdges = outgoingByTaskId.get(edge.source) ?? [];
    outgoingEdges.push(edge);
    outgoingByTaskId.set(edge.source, outgoingEdges);

    const incomingEdges = incomingByTaskId.get(edge.target) ?? [];
    incomingEdges.push(edge);
    incomingByTaskId.set(edge.target, incomingEdges);
  }

  return { incomingByTaskId, outgoingByTaskId };
}

function hasSequenceCycle(outgoingByTaskId: Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>) {
  const visitedTaskNodeIds = new Set<CrewCanvasTaskNodeId>();
  const visitingTaskNodeIds = new Set<CrewCanvasTaskNodeId>();

  for (const taskNodeId of outgoingByTaskId.keys()) {
    if (visitSequenceNode(taskNodeId, outgoingByTaskId, visitedTaskNodeIds, visitingTaskNodeIds)) return true;
  }

  return false;
}

function visitSequenceNode(
  taskNodeId: CrewCanvasTaskNodeId,
  outgoingByTaskId: Map<CrewCanvasTaskNodeId, CrewCanvasEdgeDraft[]>,
  visitedTaskNodeIds: Set<CrewCanvasTaskNodeId>,
  visitingTaskNodeIds: Set<CrewCanvasTaskNodeId>,
) {
  if (visitingTaskNodeIds.has(taskNodeId)) return true;
  if (visitedTaskNodeIds.has(taskNodeId)) return false;

  visitingTaskNodeIds.add(taskNodeId);

  for (const edge of outgoingByTaskId.get(taskNodeId) ?? []) {
    if (isTaskNodeId(edge.target) && visitSequenceNode(edge.target, outgoingByTaskId, visitedTaskNodeIds, visitingTaskNodeIds)) {
      return true;
    }
  }

  visitingTaskNodeIds.delete(taskNodeId);
  visitedTaskNodeIds.add(taskNodeId);

  return false;
}

function isTaskNodeId(value: CrewCanvasNodeId | undefined): value is CrewCanvasTaskNodeId {
  return typeof value === 'string' && value.startsWith('task:');
}
