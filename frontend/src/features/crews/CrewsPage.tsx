import { useEffect, useMemo, useState } from 'react';
import type { XYPosition } from '@xyflow/react';
import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { EmptyState } from '../../components/platform/EmptyState';
import { ErrorState } from '../../components/platform/ErrorState';
import { LoadingState } from '../../components/platform/LoadingState';
import { ActionFeedbackDialog } from '../../components/shared/ActionFeedbackDialog';
import { DeleteConfirm } from '../../components/shared/DeleteConfirm';
import { CrewBuilderCanvas } from './CrewBuilderCanvas';
import { CrewCard } from './CrewCard';
import { CrewModal } from './CrewModal';
import { CrewRow } from './CrewRow';
import { crewGraphDocumentToCanvasDraft, draftToCrewGraph } from './crewGraphAdapters';
import {
  addPlaceholderNode,
  bindCanvasNode,
  commitCanvasNodePosition,
  commitCanvasNodeSize,
  deleteCanvasEdge,
  deleteCanvasNode,
  findStaleCanvasNodeReferences,
  rebindStaleCanvasNodeReferences,
  upsertCanvasEdge,
} from './canvas/crewCanvasDraft';
import { getCrewCanvasValidation } from './canvas/crewCanvasValidation';
import type { CrewCanvasEdgeKind, CrewCanvasNodeId, CrewCanvasPlaceholderNodeId } from './canvas/crewCanvasTypes';
import {
  buildCrewGraphDocument,
  createCrewFormValues,
  type CrewCanvasDraft,
  type CrewListItem,
  useCreateCrew,
  useCrewLibrary,
  useDeleteCrew,
  useLoadCrewDraft,
  usePublishCrewDraft,
  useSaveCrewDraft,
  useUpdateCrew,
  validateCrewDraftReferences,
  useValidateCrewDraft,
} from './hooks';
import type { CrewGraphNodeId } from './crewGraphTypes';
import { getDefaultPlaceholderNodePosition, isCrewGraphNodeId } from './crewGraphTypes';

function ValueBlock({ label, value, emptyText }: { label: string; value: string; emptyText: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">{label}</p>
      <p className="mt-1 leading-6 text-stone-700">{value || emptyText}</p>
    </div>
  );
}

type FeedbackState = {
  tone: 'success' | 'danger' | 'confirm' | 'info';
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
} | null;
type BuilderAction = 'save' | 'validate' | 'publish';

const STALE_NODE_REBIND_MESSAGE = '이 캔버스의 일부 Agent/Task가 이전 버전을 참조합니다. 최신 버전으로 갱신한 뒤 계속할까요?';

function runtimeFlags(crew: CrewListItem) {
  return [crew.planning ? 'Planning' : null, crew.memory ? 'Memory' : null, crew.verbose ? 'Verbose' : null]
    .filter(Boolean)
    .join(', ');
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

function createCanvasNodeSeed() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function CrewsPage() {
  const {
    crews,
    availableAgents,
    availableTasks,
    availableTools,
    crewAssetsById,
    agentAssetsById,
    taskAssetsById,
    toolCatalogByKey,
    agentVersionTools,
    taskVersionTools,
    agentVersionToolAttachments,
    agentVersionKnowledgeAttachments,
    taskVersionToolAttachments,
    isLoading,
    isError,
    error,
  } = useCrewLibrary();
  const createCrew = useCreateCrew();
  const updateCrew = useUpdateCrew();
  const deleteCrew = useDeleteCrew();
  const loadDraft = useLoadCrewDraft();
  const saveDraft = useSaveCrewDraft();
  const validateDraft = useValidateCrewDraft();
  const publishDraft = usePublishCrewDraft();

  const [viewMode, setViewMode] = useState<'card' | 'list'>('card');
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedCrew, setSelectedCrew] = useState<CrewListItem | null>(null);
  const [activeCrewId, setActiveCrewId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CrewListItem | null>(null);
  const [draftByCrewId, setDraftByCrewId] = useState<Record<string, CrewCanvasDraft>>({});
  const [builderMessage, setBuilderMessage] = useState<string>('');
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  const [activeAction, setActiveAction] = useState<BuilderAction | null>(null);

  const emptyCrewFormValues = useMemo(() => createCrewFormValues(), []);
  const activeCrew = crews.find((crew) => crew.assetId === activeCrewId) ?? null;
  const crewAsset = activeCrew ? crewAssetsById.get(activeCrew.assetId) ?? null : null;
  const activeDraft = activeCrew ? draftByCrewId[activeCrew.assetId] ?? null : null;

  useEffect(() => {
    if (!activeCrew) {
      setBuilderMessage('');
      return;
    }

    const currentCrew = activeCrew;
    let cancelled = false;

    async function syncDraftFromBackend() {
      setBuilderMessage('');

      try {
        const envelope = await loadDraft.mutateAsync(currentCrew.assetId);
        if (cancelled) return;

        if (!envelope?.draft?.graph) {
          setDraftByCrewId((current) => ({
            ...current,
            [currentCrew.assetId]: createCrewFormValues(currentCrew).canvasDraft,
          }));
          return;
        }

        const graph = envelope.draft.graph as any;
        if (graph?.schemaVersion !== 1 || !Array.isArray(graph?.nodes) || !Array.isArray(graph?.edges)) {
          setDraftByCrewId((current) => ({
            ...current,
            [currentCrew.assetId]: createCrewFormValues(currentCrew).canvasDraft,
          }));
          return;
        }

        setDraftByCrewId((current) => ({
          ...current,
          [currentCrew.assetId]: crewGraphDocumentToCanvasDraft(graph),
        }));
      } catch (error) {
        if (cancelled) return;
        setDraftByCrewId((current) => ({
          ...current,
          [currentCrew.assetId]: createCrewFormValues(currentCrew).canvasDraft,
        }));
        setBuilderMessage(`Draft load failed: ${errorMessage(error)}`);
      }
    }

    void syncDraftFromBackend();
    return () => {
      cancelled = true;
    };
  }, [activeCrew?.assetId, activeCrew?.versionId, loadDraft.mutateAsync]);

  async function handleCreate(values: ReturnType<typeof createCrewFormValues>) {
    await createCrew.mutateAsync(values);
    setCreateOpen(false);
  }

  async function handleUpdate(values: ReturnType<typeof createCrewFormValues>) {
    if (!selectedCrew) {
      return;
    }

    await updateCrew.mutateAsync({
      assetId: selectedCrew.assetId,
      baseVersionId: selectedCrew.versionId,
      values,
      currentPayload: selectedCrew.payload,
    });
    setSelectedCrew(null);
  }

  async function handleDelete() {
    if (!deleteTarget) {
      return;
    }

    await deleteCrew.mutateAsync(deleteTarget.assetId);
    if (activeCrewId === deleteTarget.assetId) setActiveCrewId(null);
    setDeleteTarget(null);
  }

  function updateActiveDraft(nextDraft: CrewCanvasDraft) {
    if (!activeCrew) return;
    setDraftByCrewId((current) => ({ ...current, [activeCrew.assetId]: nextDraft }));
  }

  function closeFeedback() {
    setFeedback(null);
  }

  function selectNode(nodeId: CrewGraphNodeId | null) {
    if (!activeDraft) return;
    updateActiveDraft({ ...activeDraft, selectedNodeId: nodeId as CrewCanvasNodeId | null });
  }

  function addFirstNode() {
    if (!activeDraft) return;
    addNode();
  }

  function addNode(position?: XYPosition) {
    if (!activeDraft) return;

    const nodeId = `placeholder:${createCanvasNodeSeed()}` as CrewCanvasPlaceholderNodeId;
    const nextPosition = position ?? getDefaultPlaceholderNodePosition(activeDraft.nodes.length);
    updateActiveDraft({
      ...addPlaceholderNode(activeDraft, { nodeId, position: nextPosition }),
      selectedNodeId: nodeId,
    });
  }

  function assignAgentNode(nodeId: CrewCanvasNodeId, agentAssetId: string) {
    if (!activeDraft || !agentAssetId) return;
    const agentAsset = agentAssetsById.get(agentAssetId);
    if (!agentAsset) return;

    updateActiveDraft(
      bindCanvasNode(activeDraft, nodeId, {
        kind: 'agent',
        assetId: agentAsset.id,
        versionId: agentAsset.current_version.id,
      }),
    );
  }

  function assignTaskNode(nodeId: CrewCanvasNodeId, taskAssetId: string) {
    if (!activeDraft || !taskAssetId) return;
    const taskAsset = taskAssetsById.get(taskAssetId);
    if (!taskAsset) return;

    updateActiveDraft(
      bindCanvasNode(activeDraft, nodeId, {
        kind: 'task',
        assetId: taskAsset.id,
        versionId: taskAsset.current_version.id,
      }),
    );
  }

  function removeGraphNode(nodeId: CrewCanvasNodeId) {
    if (!activeDraft) return;
    updateActiveDraft(deleteCanvasNode(activeDraft, nodeId));
  }

  function connectCanvasEdge(edge: { kind: CrewCanvasEdgeKind; source: CrewCanvasNodeId; target: CrewCanvasNodeId }) {
    if (!activeDraft) return;
    const edgeId = `${edge.kind}:${edge.source}:${edge.target}`;
    const nextDraft = upsertCanvasEdge(activeDraft, { id: edgeId, ...edge });

    updateActiveDraft(nextDraft);
  }

  function removeCanvasEdge(edgeId: string) {
    if (!activeDraft) return;
    updateActiveDraft(deleteCanvasEdge(activeDraft, edgeId));
  }

  function handleBuilderNodePositionCommit(nodeId: CrewGraphNodeId, position: XYPosition) {
    if (!activeDraft) return;
    if (!isCrewGraphNodeId(nodeId) || nodeId.startsWith('crew:')) return;

    updateActiveDraft(commitCanvasNodePosition(activeDraft, nodeId as CrewCanvasNodeId, position));
  }

  function handleBuilderNodeSizeCommit(nodeId: CrewGraphNodeId, size: { width: number; height: number }) {
    if (!activeDraft) return;
    if (!isCrewGraphNodeId(nodeId) || !nodeId.startsWith('crew:')) return;

    const currentSize = activeDraft.nodeSizes?.[nodeId];
    if (currentSize?.width === size.width && currentSize.height === size.height) return;

    updateActiveDraft(commitCanvasNodeSize(activeDraft, nodeId as CrewCanvasNodeId, size));
  }

  function handleAutoLayout() {
    if (!activeDraft) return;
    updateActiveDraft({ ...activeDraft, nodePositions: {} });
    setBuilderMessage('Canvas aligned.');
  }

  const builderGraph = useMemo(() => {
    if (!activeDraft) {
      return { nodes: [], edges: [] };
    }

    return draftToCrewGraph({
      draft: activeDraft,
      crew: activeCrew
        ? {
            assetId: activeCrew.assetId,
            name: activeCrew.name,
            description: activeCrew.description,
            status: activeCrew.status,
          }
        : undefined,
      availableAgents,
      availableTasks,
      availableTools,
    });
  }, [activeCrew, activeDraft, availableAgents, availableTasks, availableTools]);

  const draftSaveBlockedReason = useMemo(() => {
    if (!activeCrew || !activeDraft || !crewAsset) return 'Select a crew draft to save.';
    const referenceError = validateCrewDraftReferences({ draft: activeDraft, agentAssetsById, taskAssetsById });
    if (referenceError) return referenceError;
    const validation = getCrewCanvasValidation(activeDraft, { process: activeCrew.process, action: 'save' });
    return validation.errors[0]?.message ?? '';
  }, [activeCrew, activeDraft, agentAssetsById, crewAsset, taskAssetsById]);

  const publishBlockedReason = useMemo(() => {
    if (!activeCrew || !activeDraft || !crewAsset) return 'Select a crew to publish.';
    const referenceError = validateCrewDraftReferences({ draft: activeDraft, agentAssetsById, taskAssetsById });
    if (referenceError) return referenceError;
    const validation = getCrewCanvasValidation(activeDraft, { process: activeCrew.process, action: 'publish' });
    return validation.errors[0]?.message ?? '';
  }, [activeCrew, activeDraft, agentAssetsById, crewAsset, taskAssetsById]);

  function requestCrewBuilderAction(action: BuilderAction) {
    if (!activeCrew || !activeDraft || !crewAsset) return;

    const blockedReason = action === 'save' ? draftSaveBlockedReason : publishBlockedReason;
    if (blockedReason) {
      setBuilderMessage(blockedReason);
      return;
    }

    const staleReferences = findStaleCanvasNodeReferences({ draft: activeDraft, agentAssetsById, taskAssetsById });
    if (staleReferences.length === 0) {
      void runCrewBuilderAction(action);
      return;
    }

    setFeedback({
      tone: 'confirm',
      title: '최신 버전으로 갱신할까요?',
      description: STALE_NODE_REBIND_MESSAGE,
      confirmLabel: '최신 버전으로 갱신',
      cancelLabel: '취소',
      onConfirm: () => {
        closeFeedback();
        const reboundDraft = rebindStaleCanvasNodeReferences({ draft: activeDraft, agentAssetsById, taskAssetsById });
        updateActiveDraft(reboundDraft);
        void runCrewBuilderAction(action, reboundDraft);
      },
    });
  }

  async function runCrewBuilderAction(action: BuilderAction, draftOverride?: CrewCanvasDraft) {
    if (!activeCrew || !crewAsset) return;
    const draftForAction = draftOverride ?? activeDraft;
    if (!draftForAction) return;

    setBuilderMessage('');
    setActiveAction(action);
    try {
      const graph = buildCrewGraphDocument({
        crewAsset,
        draft: draftForAction,
        agentAssetsById,
        taskAssetsById,
        toolCatalogByKey,
        agentVersionTools,
        taskVersionTools,
        agentVersionToolAttachments,
        agentVersionKnowledgeAttachments,
        taskVersionToolAttachments,
      });

      await saveDraft.mutateAsync({ crewAssetId: activeCrew.assetId, graph });

      if (action === 'validate') {
        await validateDraft.mutateAsync(activeCrew.assetId);
        setFeedback({ tone: 'success', title: 'Test validation completed.' });
        return;
      }

      if (action === 'publish') {
        const published = await publishDraft.mutateAsync(activeCrew.assetId);
        setFeedback({
          tone: 'success',
          title: published.already_published ? '이미 같은 버전이 배포되어 있습니다.' : 'Publish Completed',
        });
        return;
      }

      setFeedback({ tone: 'success', title: 'Draft saved.' });
    } catch (error) {
      const retryTitle =
        action === 'publish'
          ? '배포에 실패했습니다. 다시 시도하시겠습니까?'
          : action === 'validate'
            ? 'Test validation failed. Try again?'
            : 'Draft save failed. Try again?';
      setFeedback({
        tone: 'danger',
        title: retryTitle,
        description: errorMessage(error),
        confirmLabel: '다시 시도',
        cancelLabel: '취소',
        onConfirm: () => {
          closeFeedback();
          void requestCrewBuilderAction(action);
        },
      });
    } finally {
      setActiveAction(null);
    }
  }

  function handleDraftSave() {
    requestCrewBuilderAction('save');
  }

  function handleTestValidation() {
    requestCrewBuilderAction('validate');
  }

  function runPublishCrewDraft() {
    requestCrewBuilderAction('publish');
  }

  function handlePublish() {
    if (!activeCrew || !activeDraft || !crewAsset) return;
    if (publishBlockedReason) {
      setBuilderMessage(publishBlockedReason);
      return;
    }
    setFeedback({
      tone: 'confirm',
      title: '현재 Crew를 새 버전으로 배포하시겠습니까?',
      confirmLabel: '확인',
      cancelLabel: '취소',
      onConfirm: () => {
        closeFeedback();
        void runPublishCrewDraft();
      },
    });
  }

  const isActionPending = activeAction !== null || saveDraft.isPending || validateDraft.isPending || publishDraft.isPending;
  const isSaveActionPending = activeAction === 'save' || (activeAction === null && saveDraft.isPending);
  const isValidateActionPending = activeAction === 'validate' || (activeAction === null && validateDraft.isPending);
  const isPublishActionPending = activeAction === 'publish' || (activeAction === null && publishDraft.isPending);

  return (
    <PageFrame sidebar={<Sidebar />}>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
        <section className="pixel-panel bg-[#fff6df] p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Library</p>
              <h2 aria-label="Crew Library" className="mt-1 text-lg font-black text-[#22170f]">Crews ({crews.length})</h2>
            </div>
            <div className="flex items-center gap-2">
              <div className="inline-flex rounded-md border-2 border-[#7a5739] bg-[#f8e8c8] p-1">
                <button
                  type="button"
                  aria-pressed={viewMode === 'card'}
                  onClick={() => setViewMode('card')}
                  className={`rounded px-2.5 py-1 text-sm font-bold ${viewMode === 'card' ? 'bg-[#2f9b96] text-white' : 'text-stone-700'}`}
                >
                  Card
                </button>
                <button
                  type="button"
                  aria-pressed={viewMode === 'list'}
                  onClick={() => setViewMode('list')}
                  className={`rounded px-2.5 py-1 text-sm font-bold ${viewMode === 'list' ? 'bg-[#2f9b96] text-white' : 'text-stone-700'}`}
                >
                  List
                </button>
              </div>
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="pixel-button bg-[#2f9b96] px-3 py-1.5 text-sm font-bold text-white"
              >
                + New
              </button>
            </div>
          </div>

          {isLoading ? <LoadingState /> : null}
          {!isLoading && isError ? (
            <ErrorState message={`Unable to load crews: ${error instanceof Error ? error.message : 'Unknown error'}`} />
          ) : null}
          {!isLoading && !isError && crews.length === 0 ? (
            <EmptyState title="No crews yet" description="Create your first crew to start assembling runtime presets." />
          ) : null}

          {!isLoading && !isError && crews.length > 0 && viewMode === 'card' ? (
            <div className="grid gap-3">
              {crews.map((crew) => (
                <CrewCard
                  key={crew.assetId}
                  crew={crew}
                  isSelected={crew.assetId === activeCrewId}
                  onSelect={(nextCrew) => setActiveCrewId(nextCrew.assetId)}
                />
              ))}
            </div>
          ) : null}

          {!isLoading && !isError && crews.length > 0 && viewMode === 'list' ? (
            <div className="overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fffaf0]">
              <table className="min-w-full">
                <thead className="bg-[#f8e8c8] text-left text-xs font-bold uppercase tracking-[0.16em] text-[#7a5739]">
                  <tr>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {crews.map((crew) => (
                    <CrewRow
                      key={crew.assetId}
                      crew={crew}
                      isSelected={crew.assetId === activeCrewId}
                      onSelect={(nextCrew) => setActiveCrewId(nextCrew.assetId)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>

        <section className="pixel-panel bg-[#fff6df] p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Builder</p>
              <h2 className="mt-1 text-lg font-black text-[#22170f]">{activeCrew ? activeCrew.name : 'Select a crew'}</h2>
              {builderMessage ? <p className="mt-1 text-sm text-stone-600">{builderMessage}</p> : null}
            </div>
            <div className="flex shrink-0 flex-wrap justify-end gap-2">
              {activeCrew ? (
                <>
                  <button
                    type="button"
                    onClick={() => setSelectedCrew(activeCrew)}
                    className="pixel-button border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
                  >
                    Runtime settings
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(activeCrew)}
                    className="pixel-button border-rose-700 bg-[#fffaf0] px-4 py-2 text-sm font-bold text-rose-700 hover:bg-rose-50"
                  >
                    Delete
                  </button>
                </>
              ) : null}
            </div>
          </div>

          {!activeCrew || !activeDraft ? (
            <div className="mt-4 rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] p-5 text-sm leading-6 text-stone-600">
              Pick a crew from the library to start drafting its runtime graph. Drafts are saved per-user and can be published into a new crew version.
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              <div>
                <CrewBuilderCanvas
                  graph={builderGraph}
                  selectedNodeId={activeDraft.selectedNodeId}
                  onSelectNode={selectNode}
                  onAddFirstNode={addFirstNode}
                  onNodePositionCommit={handleBuilderNodePositionCommit}
                  onNodeSizeCommit={handleBuilderNodeSizeCommit}
                  onAutoLayout={handleAutoLayout}
                  availableAgents={availableAgents}
                  availableTasks={availableTasks}
                  onAddNode={addNode}
                  onAssignAgent={assignAgentNode}
                  onAssignTask={assignTaskNode}
                  onDeleteNode={removeGraphNode}
                  onDeleteEdge={removeCanvasEdge}
                  onConnectEdge={connectCanvasEdge}
                  onDraftSave={handleDraftSave}
                  onTestValidation={handleTestValidation}
                  onPublish={handlePublish}
                  isValidating={isValidateActionPending}
                  isDraftSaving={isSaveActionPending}
                  isPublishing={isPublishActionPending}
                  draftSaveDisabled={
                    !activeCrew ||
                    Boolean(draftSaveBlockedReason) ||
                    loadDraft.isPending ||
                    isActionPending
                  }
                  testValidationDisabled={
                    !activeCrew ||
                    Boolean(publishBlockedReason) ||
                    loadDraft.isPending ||
                    isActionPending
                  }
                  testValidationDisabledReason={publishBlockedReason}
                  publishDisabled={
                    Boolean(publishBlockedReason) ||
                    loadDraft.isPending ||
                    isActionPending
                  }
                  publishDisabledReason={publishBlockedReason}
                />
              </div>

              <div className="rounded-md border-2 border-[#7a5739] bg-[#f8e8c8] p-3 text-stone-800">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  <ValueBlock label="Process" value={activeCrew.processType} emptyText="Process not set." />
                  <ValueBlock label="Manager" value={activeCrew.managerAgentName} emptyText="No manager selected." />
                  <ValueBlock label="Runtime flags" value={runtimeFlags(activeCrew)} emptyText="Default runtime settings." />
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      <CrewModal
        open={createOpen}
        mode="create"
        resetKey="crew:create"
        initialValues={emptyCrewFormValues}
        availableAgents={availableAgents}
        isSubmitting={createCrew.isPending}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />

      <CrewModal
        open={selectedCrew !== null}
        mode="edit"
        resetKey={selectedCrew ? `${selectedCrew.assetId}:${selectedCrew.versionId}` : 'crew:edit'}
        initialValues={selectedCrew ? createCrewFormValues(selectedCrew) : emptyCrewFormValues}
        availableAgents={availableAgents}
        isSubmitting={updateCrew.isPending}
        onClose={() => setSelectedCrew(null)}
        onSubmit={handleUpdate}
      />

      <DeleteConfirm
        open={deleteTarget !== null}
        title="Delete crew"
        message={deleteTarget ? `Delete ${deleteTarget.name}? This removes the asset from the library.` : 'Delete this crew?'}
        isPending={deleteCrew.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
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
    </PageFrame>
  );
}
