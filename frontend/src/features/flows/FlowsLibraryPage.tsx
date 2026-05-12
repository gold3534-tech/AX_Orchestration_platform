import { useEffect, useMemo, useState } from 'react';
import type { XYPosition } from '@xyflow/react';
import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { EmptyState } from '../../components/platform/EmptyState';
import { ActionButton } from '../../components/shared/ActionButton';
import { ActionFeedbackDialog } from '../../components/shared/ActionFeedbackDialog';
import { DeleteConfirm } from '../../components/shared/DeleteConfirm';
import { FlowBuilderCanvas } from './FlowBuilderCanvas';
import { FlowMetadataModal, type FlowMetadataValues } from './FlowMetadataModal';
import { FlowTestConsole } from './FlowTestConsole';
import { draftToFlowGraph, flowGraphDocumentToCanvasDraft } from './flowGraphAdapters';
import {
  createEmptyFlowCanvasDraft,
  useCreateFlow,
  useDeleteFlow,
  useFlowCompatibilityDiagnostics,
  useFlowLibrary,
  useFlowToolMockCallDiagnostics,
  useLoadFlowDraft,
  usePublishedCrewsForFlow,
  usePublishFlowDraft,
  useSaveFlowDraft,
  useUpdateFlow,
  useValidateFlowDraft,
  type FlowCanvasDraft,
  type FlowCanvasNodeDraft,
  type PublishedCrewOption,
} from './hooks';
import { defaultFlowNodePosition, toFlowNodeId, type FlowGraphNodeId, type FlowNodeKind } from './flowGraphTypes';
import { findUnresolvedFlowInputs, formatUnresolvedFlowInputs } from './canvas/inputBindings';

const SINGLETON_NODE_KINDS = new Set<FlowNodeKind>(['input', 'start', 'output']);
const emptyFlowMetadataValues: FlowMetadataValues = { name: '', description: '' };
const TOPIC_INPUT_FIELD = {
  name: 'topic',
  type: 'string',
  required: true,
  description: 'Runtime keyword supplied from the Run page.',
};
export const FLOW_AUTO_INPUT_NODE_POSITION: XYPosition = { x: 64, y: 180 };
type DraftLoadState = 'idle' | 'loading' | 'loaded' | 'error';
type BuilderAction = 'save' | 'validate' | 'publish';
type FeedbackState = {
  tone: 'success' | 'danger' | 'confirm' | 'info';
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
} | null;

function defaultNodeData(kind: FlowNodeKind, crew?: PublishedCrewOption): FlowCanvasNodeDraft['data'] {
  if (kind === 'start') {
    return { triggerType: 'manual' };
  }

  if (kind === 'input') {
    return { fields: [] };
  }

  if (kind === 'output') {
    return { fields: [] };
  }

  if (kind === 'router') {
    return { conditions: [] };
  }

  if (kind === 'hitl') {
    return {
      label: 'HITL',
      maxAttempts: 3,
    };
  }

  return crew
    ? {
        assetId: crew.assetId,
        versionId: crew.versionId,
        inputMappings: {},
      }
    : {};
}

function nextNodeId(kind: FlowNodeKind, draft: FlowCanvasDraft, baseId?: string): FlowGraphNodeId {
  const preferredId = toFlowNodeId(kind, baseId ?? (SINGLETON_NODE_KINDS.has(kind) ? 'main' : `${kind}-${Date.now()}`));
  const existingIds = new Set(draft.nodes.map((node) => node.id));

  if (!existingIds.has(preferredId)) {
    return preferredId;
  }

  let index = 2;
  let candidate = toFlowNodeId(kind, `${baseId ?? kind}-${index}`);

  while (existingIds.has(candidate)) {
    index += 1;
    candidate = toFlowNodeId(kind, `${baseId ?? kind}-${index}`);
  }

  return candidate;
}

function crewRequiresTopic(crew: PublishedCrewOption) {
  const requiredInputs = crew.runtimeSnapshot.required_inputs;
  return Array.isArray(requiredInputs) && requiredInputs.includes('topic');
}

function ensureTopicInputNode(draft: FlowCanvasDraft): FlowCanvasDraft {
  const inputNode = draft.nodes.find((node) => node.type === 'input');
  if (!inputNode) {
    return {
      ...draft,
      nodes: [
        ...draft.nodes,
        {
          id: nextNodeId('input', draft),
          type: 'input',
          position: FLOW_AUTO_INPUT_NODE_POSITION,
          data: { fields: [TOPIC_INPUT_FIELD] },
        },
      ],
    };
  }

  const fields = Array.isArray(inputNode.data.fields) ? inputNode.data.fields : [];
  if (fields.some((field) => field && typeof field === 'object' && 'name' in field && field.name === 'topic')) {
    return draft;
  }

  return {
    ...draft,
    nodes: draft.nodes.map((node) =>
      node.id === inputNode.id
        ? {
            ...node,
            data: {
              ...node.data,
              fields: [...fields, TOPIC_INPUT_FIELD],
            },
          }
        : node,
    ),
  };
}

function errorMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  if (typeof error === 'string') {
    return error;
  }
  return 'Unknown error';
}

export function FlowsLibraryPage() {
  const flowLibrary = useFlowLibrary();
  const publishedCrewsQuery = usePublishedCrewsForFlow();
  const loadDraft = useLoadFlowDraft();
  const saveDraft = useSaveFlowDraft();
  const validateDraft = useValidateFlowDraft();
  const compatibilityDiagnostics = useFlowCompatibilityDiagnostics();
  const toolMockCallDiagnostics = useFlowToolMockCallDiagnostics();
  const publishDraft = usePublishFlowDraft();
  const createFlow = useCreateFlow();
  const updateFlow = useUpdateFlow();
  const deleteFlow = useDeleteFlow();
  const flows = flowLibrary.flows;
  const publishedCrews = publishedCrewsQuery.publishedCrews;
  const [activeFlowId, setActiveFlowId] = useState('');
  const [isCreateFlowOpen, setIsCreateFlowOpen] = useState(false);
  const [newFlowValues, setNewFlowValues] = useState<FlowMetadataValues>(emptyFlowMetadataValues);
  const [isEditFlowOpen, setIsEditFlowOpen] = useState(false);
  const [isTestConsoleOpen, setIsTestConsoleOpen] = useState(false);
  const [editFlowValues, setEditFlowValues] = useState<FlowMetadataValues>(emptyFlowMetadataValues);
  const [deleteTargetFlowId, setDeleteTargetFlowId] = useState<string | null>(null);
  const [draftByFlowId, setDraftByFlowId] = useState<Record<string, FlowCanvasDraft>>({});
  const [draftLoadStateByFlowId, setDraftLoadStateByFlowId] = useState<Record<string, DraftLoadState>>({});
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  const [activeAction, setActiveAction] = useState<BuilderAction | null>(null);
  const activeFlow = flows.find((flow) => flow.assetId === activeFlowId) ?? flows[0] ?? null;
  const activeFlowAssetId = activeFlow?.assetId ?? '';
  const deleteTargetFlow = deleteTargetFlowId
    ? flows.find((flow) => flow.assetId === deleteTargetFlowId) ?? null
    : null;
  const activeDraft = activeFlowAssetId ? draftByFlowId[activeFlowAssetId] ?? null : null;
  const activeDraftLoadState = activeFlowAssetId ? draftLoadStateByFlowId[activeFlowAssetId] ?? 'idle' : 'idle';
  const isActiveDraftReady = Boolean(activeDraft && activeDraftLoadState === 'loaded');
  const graph = useMemo(() => {
    if (!activeDraft) {
      return null;
    }

    return draftToFlowGraph({ draft: activeDraft, publishedCrews });
  }, [activeDraft, publishedCrews]);

  useEffect(() => {
    if (!activeFlowId && flows[0]) {
      setActiveFlowId(flows[0].assetId);
    }
  }, [activeFlowId, flows]);

  useEffect(() => {
    if (!activeFlowAssetId || draftByFlowId[activeFlowAssetId] || activeDraftLoadState === 'loading' || activeDraftLoadState === 'loaded') {
      return;
    }

    const flowAssetId = activeFlowAssetId;

    setDraftLoadStateByFlowId((current) => ({ ...current, [flowAssetId]: 'loading' }));

    loadDraft.mutateAsync(flowAssetId)
      .then((envelope) => {
        setDraftByFlowId((current) => {
          if (current[flowAssetId]) {
            return current;
          }

          return {
            ...current,
            [flowAssetId]: envelope?.draft?.graph
              ? flowGraphDocumentToCanvasDraft(envelope.draft.graph)
              : createEmptyFlowCanvasDraft(),
          };
        });
        setDraftLoadStateByFlowId((current) => ({ ...current, [flowAssetId]: 'loaded' }));
      })
      .catch(() => {
        setDraftLoadStateByFlowId((current) => ({ ...current, [flowAssetId]: 'error' }));
      });
  }, [activeDraftLoadState, activeFlowAssetId, draftByFlowId, loadDraft]);

  function updateDraft(nextDraft: FlowCanvasDraft) {
    if (!activeFlow) {
      return;
    }

    setDraftByFlowId((current) => ({ ...current, [activeFlow.assetId]: nextDraft }));
  }

  function openCreateFlow() {
    setNewFlowValues(emptyFlowMetadataValues);
    setIsCreateFlowOpen(true);
  }

  function closeFeedback() {
    setFeedback(null);
  }

  function unresolvedInputMessage() {
    if (!activeDraft) {
      return '';
    }

    return formatUnresolvedFlowInputs(findUnresolvedFlowInputs(activeDraft, publishedCrews));
  }

  function hasUnresolvedInputs() {
    return unresolvedInputMessage().length > 0;
  }

  function showUnresolvedInputsDialog({
    allowSaveAnyway,
    onSaveAnyway,
  }: {
    allowSaveAnyway: boolean;
    onSaveAnyway?: () => void;
  }) {
    const description = unresolvedInputMessage();

    setFeedback({
      tone: allowSaveAnyway ? 'confirm' : 'danger',
      title: 'Unresolved Flow inputs',
      description,
      confirmLabel: allowSaveAnyway ? 'Save draft anyway' : '확인',
      cancelLabel: allowSaveAnyway ? '취소' : undefined,
      onConfirm: allowSaveAnyway
        ? () => {
            closeFeedback();
            onSaveAnyway?.();
          }
        : closeFeedback,
    });
  }

  function addNode(kind: FlowNodeKind, position: XYPosition = defaultFlowNodePosition(kind)) {
    if (!activeDraft || !isActiveDraftReady) {
      return;
    }

    const existingSingleton = SINGLETON_NODE_KINDS.has(kind)
      ? activeDraft.nodes.find((node) => node.type === kind)
      : undefined;

    if (existingSingleton) {
      updateDraft({ ...activeDraft, selectedNodeId: existingSingleton.id });
      return;
    }

    const id = nextNodeId(kind, activeDraft);
    updateDraft({
      ...activeDraft,
      selectedNodeId: id,
      nodes: [
        ...activeDraft.nodes,
        {
          id,
          type: kind,
          position,
          data: defaultNodeData(kind),
        },
      ],
    });
  }

  function addCrewNode(position: XYPosition = defaultFlowNodePosition('crew'), crew: PublishedCrewOption | undefined = publishedCrews[0]) {
    if (!activeDraft || !isActiveDraftReady) {
      return;
    }

    if (!crew) {
      return;
    }

    const draftWithRequiredInputs = crewRequiresTopic(crew) ? ensureTopicInputNode(activeDraft) : activeDraft;
    const id = nextNodeId('crew', draftWithRequiredInputs, crew.assetId);
    updateDraft({
      ...draftWithRequiredInputs,
      selectedNodeId: id,
      nodes: [
        ...draftWithRequiredInputs.nodes,
        {
          id,
          type: 'crew',
          position,
          data: defaultNodeData('crew', crew),
        },
      ],
    });
  }

  async function runSaveActiveDraft() {
    if (!activeFlow || !graph || !isActiveDraftReady) {
      return;
    }

    setActiveAction('save');
    try {
      await saveDraft.mutateAsync({ flowAssetId: activeFlow.assetId, graph });
      setFeedback({ tone: 'success', title: 'Draft saved.' });
    } catch (error) {
      setFeedback({
        tone: 'danger',
        title: 'Draft save failed. Try again?',
        description: errorMessage(error),
        confirmLabel: '다시 시도',
        cancelLabel: '취소',
        onConfirm: () => {
          closeFeedback();
          void runSaveActiveDraft();
        },
      });
    } finally {
      setActiveAction(null);
    }
  }

  function saveActiveDraft() {
    if (!activeFlow || !graph || !isActiveDraftReady) {
      return;
    }

    if (hasUnresolvedInputs()) {
      showUnresolvedInputsDialog({
        allowSaveAnyway: true,
        onSaveAnyway: () => {
          void runSaveActiveDraft();
        },
      });
      return;
    }

    void runSaveActiveDraft();
  }

  async function saveActiveDraftForConsole() {
    if (!activeFlow || !graph || !isActiveDraftReady) {
      throw new Error('Flow draft is not ready.');
    }

    await saveDraft.mutateAsync({ flowAssetId: activeFlow.assetId, graph });
  }

  async function runValidateGraphFromConsole() {
    if (!activeFlow) {
      throw new Error('Select a Flow before testing.');
    }
    setActiveAction('validate');
    try {
      await saveActiveDraftForConsole();
      return await validateDraft.mutateAsync(activeFlow.assetId);
    } finally {
      setActiveAction(null);
    }
  }

  async function runCompatibilityFromConsole() {
    if (!activeFlow) {
      throw new Error('Select a Flow before testing.');
    }
    await saveActiveDraftForConsole();
    return compatibilityDiagnostics.mutateAsync({ flowAssetId: activeFlow.assetId, inputs: {} });
  }

  async function runToolMockCallFromConsole() {
    if (!activeFlow) {
      throw new Error('Select a Flow before testing.');
    }
    await saveActiveDraftForConsole();
    return toolMockCallDiagnostics.mutateAsync(activeFlow.assetId);
  }

  async function runPublishActiveDraft() {
    if (!activeFlow || !graph || !isActiveDraftReady) {
      return;
    }

    setActiveAction('publish');
    try {
      await saveDraft.mutateAsync({ flowAssetId: activeFlow.assetId, graph });
      const result = await publishDraft.mutateAsync(activeFlow.assetId);
      setFeedback({
        tone: 'success',
        title: result.already_published ? '이미 같은 버전이 배포되어 있습니다.' : 'Publish Completed',
      });
    } catch (error) {
      setFeedback({
        tone: 'danger',
        title: '배포에 실패했습니다. 다시 시도하시겠습니까?',
        description: errorMessage(error),
        confirmLabel: '다시 시도',
        cancelLabel: '취소',
        onConfirm: () => {
          closeFeedback();
          void runPublishActiveDraft();
        },
      });
    } finally {
      setActiveAction(null);
    }
  }

  function publishActiveDraft() {
    if (!activeFlow || !graph || !isActiveDraftReady) {
      return;
    }

    if (hasUnresolvedInputs()) {
      showUnresolvedInputsDialog({ allowSaveAnyway: false });
      return;
    }

    setFeedback({
      tone: 'confirm',
      title: '현재 Flow를 새 버전으로 배포하시겠습니까?',
      confirmLabel: '확인',
      cancelLabel: '취소',
      onConfirm: () => {
        closeFeedback();
        void runPublishActiveDraft();
      },
    });
  }

  async function createNewFlow(values: FlowMetadataValues) {
    const name = values.name.trim();
    if (!name) {
      return;
    }

    const createdFlow = await createFlow.mutateAsync({
      name,
      description: values.description.trim(),
    });

    setIsCreateFlowOpen(false);
    setNewFlowValues(emptyFlowMetadataValues);

    if (createdFlow?.id) {
      setActiveFlowId(createdFlow.id);
    }
  }

  function openEditFlow() {
    if (!activeFlow) {
      return;
    }

    setEditFlowValues({
      name: activeFlow.name,
      description: activeFlow.description,
    });
    setIsEditFlowOpen(true);
  }

  async function updateActiveFlowMetadata(values: FlowMetadataValues) {
    if (!activeFlow) {
      return;
    }

    const activeAsset = flowLibrary.flowAssetsById.get(activeFlow.assetId);
    const currentVersion = activeAsset?.current_version;
    const currentPayload = currentVersion?.payload;
    const payload =
      currentPayload && typeof currentPayload === 'object' && !Array.isArray(currentPayload)
        ? (currentPayload as Record<string, unknown>)
        : {};

    try {
      await updateFlow.mutateAsync({
        assetId: activeFlow.assetId,
        baseVersionId: currentVersion?.id ?? activeFlow.versionId,
        name: values.name,
        description: values.description,
        payload,
      });
      setIsEditFlowOpen(false);
    } catch (error) {
      setIsEditFlowOpen(false);
      setFeedback({
        tone: 'danger',
        title: 'Flow update failed. Try again?',
        description: errorMessage(error),
        confirmLabel: '확인',
      });
    }
  }

  async function deleteActiveFlow() {
    if (!deleteTargetFlowId) {
      return;
    }

    const flowId = deleteTargetFlowId;
    try {
      await deleteFlow.mutateAsync(flowId);

      setDraftByFlowId((current) => {
        const { [flowId]: _deletedDraft, ...remainingDrafts } = current;
        return remainingDrafts;
      });

      if (activeFlowAssetId === flowId) {
        setActiveFlowId('');
      }

      setDeleteTargetFlowId(null);
    } catch (error) {
      setDeleteTargetFlowId(null);
      setFeedback({
        tone: 'danger',
        title: 'Flow delete failed.',
        description: errorMessage(error),
        confirmLabel: '확인',
      });
    }
  }

  const createFlowModal = (
    <FlowMetadataModal
      open={isCreateFlowOpen}
      title="New flow"
      submitLabel="Create Flow"
      initialValues={newFlowValues}
      isSubmitting={createFlow.isPending}
      onClose={() => {
        setIsCreateFlowOpen(false);
        setNewFlowValues(emptyFlowMetadataValues);
      }}
      onSubmit={createNewFlow}
    />
  );

  const editFlowModal = (
    <FlowMetadataModal
      open={isEditFlowOpen}
      title="Edit flow"
      submitLabel="Save changes"
      initialValues={editFlowValues}
      isSubmitting={updateFlow.isPending}
      onClose={() => setIsEditFlowOpen(false)}
      onSubmit={updateActiveFlowMetadata}
    />
  );

  const deleteConfirm = (
    <DeleteConfirm
      open={deleteTargetFlowId !== null}
      title="Delete flow"
      message={deleteTargetFlow ? `Delete ${deleteTargetFlow.name}? This removes the asset from the library.` : 'Delete this flow?'}
      isPending={deleteFlow.isPending}
      onCancel={() => setDeleteTargetFlowId(null)}
      onConfirm={deleteActiveFlow}
    />
  );

  const actionFeedbackDialog = (
    <ActionFeedbackDialog
      open={Boolean(feedback)}
      tone={feedback?.tone}
      title={feedback?.title ?? ''}
      description={feedback?.description}
      confirmLabel={feedback?.confirmLabel ?? '확인'}
      cancelLabel={feedback?.cancelLabel}
      onConfirm={feedback?.onConfirm ?? closeFeedback}
      onCancel={closeFeedback}
    />
  );

  if (flowLibrary.isLoading) {
    return (
      <PageFrame sidebar={<Sidebar />}>
        <EmptyState title="Loading flows" description="Preparing Flow Builder." />
      </PageFrame>
    );
  }

  if (flowLibrary.isError) {
    return (
      <PageFrame sidebar={<Sidebar />}>
        <EmptyState title="Unable to load flows" description="Refresh the page and try opening Flow Builder again." />
      </PageFrame>
    );
  }

  if (!activeFlow) {
    return (
      <PageFrame sidebar={<Sidebar />}>
        <div className="flex min-h-[calc(100vh-88px)] flex-col gap-4">
          <header className="pixel-panel flex flex-wrap items-center justify-between gap-3 bg-[#fff6df] px-4 py-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#2f9b96]">Flow Library</p>
              <h1 className="text-2xl font-black text-[#22170f]">Flow Builder</h1>
              <p className="mt-1 text-sm text-stone-600">Create a Flow to start building on the canvas.</p>
            </div>
            <button
              type="button"
              onClick={openCreateFlow}
              className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa]"
            >
              + New Flow
            </button>
          </header>
          <EmptyState title="No flows yet" description="Create a Flow to start building." />
        </div>
        {actionFeedbackDialog}
        {createFlowModal}
        {editFlowModal}
        {deleteConfirm}
      </PageFrame>
    );
  }

  const isDraftLoading = activeDraftLoadState === 'idle' || activeDraftLoadState === 'loading';
  const isBuilderDisabled = !isActiveDraftReady;
  const isDiagnosticActionPending = compatibilityDiagnostics.isPending || toolMockCallDiagnostics.isPending;
  const isActionPending = activeAction !== null || saveDraft.isPending || validateDraft.isPending || publishDraft.isPending || isDiagnosticActionPending;
  const isSaveActionPending = activeAction === 'save' || (activeAction === null && saveDraft.isPending);
  const isPublishActionPending = activeAction === 'publish' || (activeAction === null && publishDraft.isPending);
  const isMetadataActionPending = updateFlow.isPending || deleteFlow.isPending;

  return (
    <PageFrame sidebar={<Sidebar />}>
      <div className="flex min-h-[calc(100vh-88px)] flex-col gap-4">
        <header className="pixel-panel flex flex-wrap items-center justify-between gap-3 bg-[#fff6df] px-4 py-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#2f9b96]">Flow Library</p>
            <h1 className="text-2xl font-black text-[#22170f]">Flow Builder</h1>
            <p className="mt-1 text-sm text-stone-600">Build, save, validate, and publish the active Flow graph.</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Select flow"
              value={activeFlow.assetId}
              onChange={(event) => setActiveFlowId(event.target.value)}
              disabled={isTestConsoleOpen || isActionPending || isMetadataActionPending}
              className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] shadow-[3px_3px_0_#7a5739]"
            >
              {flows.map((flow) => (
                <option key={flow.assetId} value={flow.assetId}>
                  {flow.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={openCreateFlow}
              className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa]"
            >
              + New Flow
            </button>
            <ActionButton
              variant="secondary"
              onClick={openEditFlow}
              disabled={!activeFlow || isActionPending || isMetadataActionPending}
            >
              Edit
            </ActionButton>
            <ActionButton
              variant="secondary"
              onClick={() => setDeleteTargetFlowId(activeFlow.assetId)}
              disabled={!activeFlow || isActionPending || isMetadataActionPending}
              isPending={deleteFlow.isPending}
              pendingLabel="Deleting..."
              className="border-rose-300 text-rose-700 hover:border-rose-300 hover:bg-rose-50"
            >
              Delete
            </ActionButton>
            <ActionButton
              variant="soft"
              onClick={saveActiveDraft}
              disabled={isBuilderDisabled || isActionPending || isMetadataActionPending}
              isPending={isSaveActionPending}
              pendingLabel="Saving..."
            >
              Draft Save
            </ActionButton>
            <ActionButton
              variant="secondary"
              onClick={() => setIsTestConsoleOpen(true)}
              disabled={isBuilderDisabled || isActionPending || isMetadataActionPending}
            >
              Test
            </ActionButton>
            <ActionButton
              variant="primary"
              onClick={publishActiveDraft}
              disabled={isBuilderDisabled || isActionPending || isMetadataActionPending}
              isPending={isPublishActionPending}
              pendingLabel="Publishing..."
            >
              Publish
            </ActionButton>
          </div>
        </header>

        {isDraftLoading ? (
          <EmptyState title="Loading flow draft" description="Preparing the saved draft before editing is enabled." />
        ) : activeDraftLoadState === 'error' ? (
          <EmptyState title="Unable to load flow draft" description="Refresh the page before editing this Flow." />
        ) : activeDraft ? (
          <FlowBuilderCanvas
            draft={activeDraft}
            publishedCrews={publishedCrews}
            onAddNode={addNode}
            onAddCrew={addCrewNode}
            onSelectNode={(nodeId) => updateDraft({ ...activeDraft, selectedNodeId: nodeId })}
            onChangeDraft={updateDraft}
            showTopAddCrew={false}
          />
        ) : (
          <EmptyState title="Loading flow draft" description="Preparing the saved draft before editing is enabled." />
        )}
      </div>
      {actionFeedbackDialog}
      {createFlowModal}
      {editFlowModal}
      {deleteConfirm}
      <FlowTestConsole
        key={`${activeFlow.assetId}:${isTestConsoleOpen ? 'open' : 'closed'}`}
        open={isTestConsoleOpen}
        flowAssetId={activeFlow.assetId}
        flowName={activeFlow.name}
        onClose={() => setIsTestConsoleOpen(false)}
        onValidateGraph={runValidateGraphFromConsole}
        onCompatibilityTest={runCompatibilityFromConsole}
        onToolMockCallCheck={runToolMockCallFromConsole}
        isBusy={
          activeAction !== null ||
          saveDraft.isPending ||
          validateDraft.isPending ||
          compatibilityDiagnostics.isPending ||
          toolMockCallDiagnostics.isPending
        }
      />
    </PageFrame>
  );
}
