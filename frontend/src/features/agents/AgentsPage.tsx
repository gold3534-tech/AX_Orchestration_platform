import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getLlmCatalog } from '../../api/llmCatalog';
import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { EmptyState } from '../../components/platform/EmptyState';
import { ErrorState } from '../../components/platform/ErrorState';
import { LoadingState } from '../../components/platform/LoadingState';
import { PageHeader } from '../../components/platform/PageHeader';
import { DeleteConfirm } from '../../components/shared/DeleteConfirm';
import { queryKeys } from '../../hooks/queryKeys';
import { AgentCard } from './AgentCard';
import { AgentModal } from './AgentModal';
import { AgentRow } from './AgentRow';
import type { AgentAttachmentValues, AgentFormValues, AgentInputPresetOption, AgentListItem } from './hooks';
import { useAgentsLibrary, useCreateAgent, useDeleteAgent, useUpdateAgent } from './hooks';
import { modelOptionsFromCatalog } from './llmCatalog';

const emptyAgentFormValues: AgentFormValues = {
  role: '',
  goal: '',
  backstory: '',
};

export function toFormValues(agent: AgentListItem): AgentFormValues {
  return {
    role: agent.role,
    goal: agent.goal,
    backstory: agent.backstory,
    llm: agent.llm,
    llmProvider: agent.llmProvider,
    llmTemperature: agent.llmTemperature,
    llmMaxTokens: agent.llmMaxTokens,
    function_calling_llm: agent.function_calling_llm,
    functionCallingLlmProvider: agent.functionCallingLlmProvider,
    max_iter: agent.max_iter,
    max_rpm: agent.max_rpm,
    max_execution_time: agent.max_execution_time,
    verbose: agent.verbose,
    allow_delegation: agent.allow_delegation ?? agent.allowDelegation,
    reasoning: agent.reasoning,
    max_reasoning_attempts: agent.max_reasoning_attempts,
    cache: agent.cache,
    respect_context_window: agent.respect_context_window,
    max_retry_limit: agent.max_retry_limit,
    multimodal: agent.multimodal,
    inject_date: agent.inject_date,
    date_format: agent.date_format,
    embedder: agent.embedder,
  };
}

function toAttachmentValues(agent: AgentListItem): AgentAttachmentValues {
  return {
    tools: [...agent.tools],
    toolConfigs: { ...(agent.toolConfigs ?? {}) },
    knowledgeSources: [...(agent.knowledgeSources ?? [])],
  };
}

function readPresetLabels(keys: string[], presetLabels: Map<string, string>) {
  if (keys.length === 0) {
    return '';
  }

  return keys.map((key) => presetLabels.get(key) ?? key).join(', ');
}

function ValueBlock({ label, value, emptyText }: { label: string; value: string; emptyText: string }) {
  return (
    <div>
      <p className="font-ax-label text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">{label}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm font-medium leading-6 text-stone-700">{value || emptyText}</p>
    </div>
  );
}

function AgentInspector({
  agent,
  inputPresets,
}: {
  agent: AgentListItem | null;
  inputPresets: AgentInputPresetOption[];
}) {
  const presetLabels = new Map(inputPresets.map((preset) => [preset.key, preset.label]));

  if (!agent) {
    return (
      <div className="mt-6 rounded-md border-2 border-dashed border-[#9a7a54] bg-[#fff6df] p-5 text-sm font-semibold leading-6 text-stone-700">
        Select an agent card or list row to inspect details and manage it here.
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-5">
      <div className="rounded-md border-2 border-[#9a7a54] bg-[#fff6df] p-4 shadow-[3px_3px_0_rgba(80,48,24,0.16)] 2xl:p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h3 className="truncate text-xl font-black text-stone-950 2xl:text-2xl">{agent.name}</h3>
            <p className="mt-2 text-sm font-semibold text-stone-700">{agent.role || 'Role not set'}</p>
          </div>
        </div>
      </div>

      <div className="space-y-4 rounded-md border-2 border-[#9a7a54] bg-[#fff6df] p-4 shadow-[3px_3px_0_rgba(80,48,24,0.16)] 2xl:space-y-5 2xl:p-5">
        <ValueBlock label="Goal" value={agent.goal} emptyText="No goal has been written yet." />
        <ValueBlock label="Backstory" value={agent.backstory} emptyText="No backstory has been written yet." />
        <ValueBlock
          label="Delegation"
          value={agent.allowDelegation ? 'Allowed' : 'Disabled'}
          emptyText="Disabled"
        />
        <ValueBlock label="Tools" value={agent.tools.join(', ')} emptyText="No tools attached." />
        <ValueBlock
          label="Input presets"
          value={readPresetLabels(agent.inputPresets ?? [], presetLabels)}
          emptyText="No input presets attached."
        />
      </div>
    </div>
  );
}

export function AgentsPage() {
  const {
    agents,
    agentPayloadsByAssetId = new Map<string, Record<string, unknown>>(),
    inputPresets = [],
    toolCatalog = [],
    isLoading,
    isError,
    error,
    presetCatalogError = null,
    isPresetCatalogLoading = false,
    knowledgeSources = [],
  } = useAgentsLibrary();
  const createAgent = useCreateAgent();
  const updateAgent = useUpdateAgent();
  const deleteAgent = useDeleteAgent();
  const [viewMode, setViewMode] = useState<'card' | 'list'>('card');
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<AgentListItem | null>(null);
  const [inspectorAgentId, setInspectorAgentId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AgentListItem | null>(null);
  const inspectorAgent = agents.find((agent) => agent.assetId === inspectorAgentId) ?? null;
  const llmCatalogQuery = useQuery({ queryKey: queryKeys.llmCatalog.all(), queryFn: getLlmCatalog });
  const llmModels = modelOptionsFromCatalog(llmCatalogQuery.data);
  const embedders: string[] = [];

  function handleSelectAgent(agent: AgentListItem) {
    setInspectorAgentId(agent.assetId);
  }

  async function handleCreate(values: AgentFormValues, attachments: AgentAttachmentValues) {
    await createAgent.mutateAsync({ values, attachments });
    setCreateOpen(false);
  }

  function openCreateAgentModal() {
    setCreateOpen(true);
  }

  async function handleEdit(values: AgentFormValues, attachments: AgentAttachmentValues) {
    if (!editTarget) return;
    await updateAgent.mutateAsync({
      assetId: editTarget.assetId,
      baseVersionId: editTarget.versionId,
      values,
      attachments,
      currentPayload: agentPayloadsByAssetId.get(editTarget.assetId),
    });
    setEditTarget(null);
  }

  async function handleDelete() {
    if (!deleteTarget) {
      return;
    }

    await deleteAgent.mutateAsync(deleteTarget.assetId);
    if (inspectorAgentId === deleteTarget.assetId) {
      setInspectorAgentId(null);
    }
    setDeleteTarget(null);
  }

  return (
    <PageFrame sidebar={<Sidebar />}>
      <PageHeader
        title="Agents"
        description="Build your agent library from versioned assets and keep tool / skill attachments visible."
      />

      <div className="font-ax-body grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(260px,0.58fr)]">
        <section className="rounded-md border-2 border-[#7a5739] bg-white/95 p-4 shadow-[6px_6px_0_rgba(80,48,24,0.18)] 2xl:p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="font-ax-label text-xs font-black uppercase tracking-[0.18em] text-[#2f9b96]">Library</p>
              <h2 className="mt-1 text-lg font-black text-stone-950 2xl:text-xl">Agent Library ({agents.length} total)</h2>
            </div>
            <div className="flex items-center gap-3">
              <div className="inline-flex rounded-md border-2 border-[#9a7a54] bg-[#fff6df] p-1">
                <button
                  type="button"
                  aria-pressed={viewMode === 'card'}
                  onClick={() => setViewMode('card')}
                  className={`rounded-sm px-3 py-2 text-sm font-black ${
                    viewMode === 'card' ? 'bg-[#2f9b96] text-white' : 'text-stone-700'
                  }`}
                >
                  Card
                </button>
                <button
                  type="button"
                  aria-pressed={viewMode === 'list'}
                  onClick={() => setViewMode('list')}
                  className={`rounded-sm px-3 py-2 text-sm font-black ${
                    viewMode === 'list' ? 'bg-[#2f9b96] text-white' : 'text-stone-700'
                  }`}
                >
                  List
                </button>
              </div>
              <button
                type="button"
                onClick={openCreateAgentModal}
                className="pixel-button bg-[#ef8b2c] px-4 py-2 text-sm font-black text-white"
              >
                + New
              </button>
            </div>
          </div>

          {isLoading ? <LoadingState /> : null}
          {!isLoading && isError ? <ErrorState message={`Unable to load agents: ${error instanceof Error ? error.message : 'Unknown error'}`} /> : null}
          {!isLoading && !isError && agents.length === 0 ? (
            <EmptyState title="No agents yet" description="Create your first agent to start building the library." />
          ) : null}
          {!isLoading && !isError && agents.length > 0 && viewMode === 'card' ? (
            <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))] 2xl:gap-4">
              {agents.map((agent) => (
                <AgentCard
                  key={agent.assetId}
                  agent={agent}
                  isSelected={agent.assetId === inspectorAgentId}
                  onSelect={handleSelectAgent}
                />
              ))}
            </div>
          ) : null}
          {!isLoading && !isError && agents.length > 0 && viewMode === 'list' ? (
            <div className="overflow-hidden rounded-md border-2 border-[#7a5739] bg-white">
              <table className="min-w-full">
                <thead className="bg-[#fff6df] text-left text-xs font-black uppercase tracking-[0.16em] text-stone-700">
                  <tr>
                    <th className="px-4 py-3">Photo</th>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Goal</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((agent) => (
                    <AgentRow
                      key={agent.assetId}
                      agent={agent}
                      isSelected={agent.assetId === inspectorAgentId}
                      onSelect={handleSelectAgent}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>

        <section className="rounded-md border-2 border-[#7a5739] bg-white/95 p-4 shadow-[6px_6px_0_rgba(80,48,24,0.18)] 2xl:p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-ax-label text-xs font-black uppercase tracking-[0.18em] text-[#2f9b96]">Inspector</p>
              <h2 className="mt-1 text-lg font-black text-stone-950 2xl:text-xl">Selected agent details</h2>
            </div>
            {inspectorAgent ? (
              <div className="flex shrink-0 flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setEditTarget(inspectorAgent)}
                  className="pixel-button bg-[#58b7b0] px-4 py-2 text-sm font-black text-white"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(inspectorAgent)}
                  className="pixel-button bg-[#fff6df] px-4 py-2 text-sm font-black text-rose-700 hover:bg-rose-50"
                >
                  Delete
                </button>
              </div>
            ) : null}
          </div>
          <AgentInspector
            agent={inspectorAgent}
            inputPresets={inputPresets}
          />
        </section>
      </div>

      <AgentModal
        open={createOpen}
        mode="create"
        resetKey="agent:create"
        initialValues={emptyAgentFormValues}
        availableTools={toolCatalog}
        availableKnowledgeSources={knowledgeSources}
        initialAttachments={{ tools: [], toolConfigs: {}, knowledgeSources: [] }}
        llmModels={llmModels}
        embedders={embedders}
        isSubmitting={createAgent.isPending || isPresetCatalogLoading}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />

      <AgentModal
        open={editTarget !== null}
        mode="edit"
        resetKey={editTarget ? `agent:edit:${editTarget.assetId}:${editTarget.versionId}` : 'agent:edit:closed'}
        initialValues={editTarget ? toFormValues(editTarget) : emptyAgentFormValues}
        availableTools={toolCatalog}
        availableKnowledgeSources={knowledgeSources}
        initialAttachments={editTarget ? toAttachmentValues(editTarget) : { tools: [], toolConfigs: {}, knowledgeSources: [] }}
        llmModels={llmModels}
        embedders={embedders}
        isSubmitting={updateAgent.isPending}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEdit}
      />

      {presetCatalogError ? (
        <div className="sr-only" role="alert">
          Unable to load input presets.
        </div>
      ) : null}
      {llmCatalogQuery.isError ? (
        <div className="sr-only" role="alert">
          Unable to load LLM catalog.
        </div>
      ) : null}

      <DeleteConfirm
        open={deleteTarget !== null}
        title="Delete agent"
        message={deleteTarget ? `Delete ${deleteTarget.name}? This removes the asset from the library.` : 'Delete this agent?'}
        isPending={deleteAgent.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </PageFrame>
  );
}
