import { useState } from 'react';
import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { EmptyState } from '../../components/platform/EmptyState';
import { ErrorState } from '../../components/platform/ErrorState';
import { LoadingState } from '../../components/platform/LoadingState';
import { PageHeader } from '../../components/platform/PageHeader';
import { DeleteConfirm } from '../../components/shared/DeleteConfirm';
import { TaskCard } from './TaskCard';
import { TaskModal } from './TaskModal';
import { TaskRow } from './TaskRow';
import type { TaskFormValues, TaskInputPresetOption, TaskListItem } from './hooks';
import { useCreateTask, useDeleteTask, useTasksLibrary, useUpdateTask } from './hooks';

const emptyTaskFormValues: TaskFormValues = {
  name: '',
  description: '',
  expectedOutput: '',
  outputType: 'Raw',
  outputSchemaFields: [],
  asyncExecution: undefined,
  humanInput: undefined,
  markdown: undefined,
  guardrailMaxRetries: undefined,
  outputFile: '',
  createDirectory: undefined,
  inputPresets: [],
  tools: [],
  toolConfigs: {},
};

function toFormValues(task: TaskListItem): TaskFormValues {
  return {
    name: task.name,
    description: task.description,
    expectedOutput: task.expectedOutput,
    outputType: task.outputType ?? 'Raw',
    outputSchemaFields: [...(task.outputSchemaFields ?? [])],
    asyncExecution: task.asyncExecution,
    humanInput: task.humanInput,
    markdown: task.markdown,
    guardrailMaxRetries: task.guardrailMaxRetries,
    outputFile: task.outputFile ?? '',
    createDirectory: task.createDirectory,
    inputPresets: [...(task.inputPresets ?? [])],
    tools: [...(task.tools ?? [])],
    toolConfigs: { ...(task.toolConfigs ?? {}) },
  };
}

function ValueBlock({ label, value, emptyText }: { label: string; value: string; emptyText: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-500">{label}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-stone-700">{value || emptyText}</p>
    </div>
  );
}

function readPresetLabels(keys: string[], presetLabels: Map<string, string>) {
  if (keys.length === 0) {
    return '';
  }

  return keys.map((key) => presetLabels.get(key) ?? key).join(', ');
}

function TaskInspector({
  task,
  inputPresets,
}: {
  task: TaskListItem | null;
  inputPresets: TaskInputPresetOption[];
}) {
  const presetLabels = new Map(inputPresets.map((preset) => [preset.key, preset.label]));

  if (!task) {
    return (
      <div className="mt-6 rounded-md border-2 border-dashed border-[#9a7a54] bg-[#fff6df] p-5 text-sm font-semibold leading-6 text-stone-700">
        Select a task card or list row to inspect details and manage it here.
      </div>
    );
  }

  return (
    <div className="mt-5 space-y-5">
      <div className="rounded-md border-2 border-[#9a7a54] bg-[#fff6df] p-4 shadow-[3px_3px_0_rgba(80,48,24,0.16)] 2xl:p-5">
        <div className="min-w-0">
          <h3 className="truncate text-xl font-black text-stone-950 2xl:text-2xl">{task.name}</h3>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-stone-700">
            {task.description || 'No description has been written yet.'}
          </p>
        </div>
      </div>

      <div className="space-y-4 rounded-md border-2 border-[#9a7a54] bg-[#fff6df] p-4 shadow-[3px_3px_0_rgba(80,48,24,0.16)] 2xl:space-y-5 2xl:p-5">
        <ValueBlock
          label="Expected output"
          value={task.expectedOutput}
          emptyText="No expected output has been written yet."
        />
        <ValueBlock label="Output type" value={task.outputType} emptyText="Raw" />
        <ValueBlock
          label="Input presets"
          value={readPresetLabels(task.inputPresets, presetLabels)}
          emptyText="No input presets attached."
        />
        <ValueBlock
          label="Tools"
          value={task.tools.join(', ')}
          emptyText="No tools attached."
        />
      </div>
    </div>
  );
}

export function TasksPage() {
  const {
    tasks,
    inputPresets,
    tools,
    toolCatalog = [],
    isLoading,
    isError,
    error,
    presetCatalogError,
    isPresetCatalogLoading,
    refetchPresetCatalog,
  } = useTasksLibrary();
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const deleteTask = useDeleteTask();
  const [viewMode, setViewMode] = useState<'card' | 'list'>('card');
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<TaskListItem | null>(null);
  const [inspectorTaskId, setInspectorTaskId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TaskListItem | null>(null);

  const inspectorTask = tasks.find((task) => task.assetId === inspectorTaskId) ?? null;
  const canOpenTaskForm = !isPresetCatalogLoading && presetCatalogError == null;

  function handleSelectTask(task: TaskListItem) {
    setInspectorTaskId(task.assetId);
  }

  function openCreateTaskModal() {
    void refetchPresetCatalog();
    setCreateOpen(true);
  }

  function openEditTaskModal(task: TaskListItem) {
    void refetchPresetCatalog();
    setEditTarget(task);
  }

  async function handleCreate(values: TaskFormValues) {
    await createTask.mutateAsync(values);
    setCreateOpen(false);
  }

  async function handleEdit(values: TaskFormValues) {
    if (!editTarget) {
      return;
    }

    await updateTask.mutateAsync({
      assetId: editTarget.assetId,
      baseVersionId: editTarget.versionId,
      values,
    });
    setEditTarget(null);
  }

  async function handleDelete() {
    if (!deleteTarget) {
      return;
    }

    await deleteTask.mutateAsync(deleteTarget.assetId);
    if (inspectorTaskId === deleteTarget.assetId) {
      setInspectorTaskId(null);
    }
    setDeleteTarget(null);
  }

  return (
    <PageFrame sidebar={<Sidebar />}>
      <PageHeader
        title="Tasks"
        description="Create reusable task definitions with clear descriptions, expected outputs, and friendly preset inputs."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <section className="rounded-md border-2 border-[#7a5739] bg-white/95 p-5 shadow-[6px_6px_0_rgba(80,48,24,0.18)]">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[#2f9b96]">Library</p>
              <h2 className="mt-1 text-xl font-black text-stone-950">Task Library ({tasks.length} total)</h2>
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
                onClick={openCreateTaskModal}
                disabled={!canOpenTaskForm}
                className="pixel-button bg-[#ef8b2c] px-4 py-2 text-sm font-black text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                + New
              </button>
            </div>
          </div>

          {isLoading ? <LoadingState /> : null}
          {!isLoading && isError ? (
            <ErrorState
              message={`Unable to load tasks: ${error instanceof Error ? error.message : 'Unknown error'}`}
            />
          ) : null}
          {!isLoading && !isError && tasks.length === 0 ? (
            <EmptyState title="No tasks yet" description="Create your first task to start building the library." />
          ) : null}

          {!isLoading && !isError && tasks.length > 0 && viewMode === 'card' ? (
            <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
              {tasks.map((task) => (
                <TaskCard
                  key={task.assetId}
                  task={task}
                  isSelected={task.assetId === inspectorTaskId}
                  onSelect={handleSelectTask}
                />
              ))}
            </div>
          ) : null}

          {!isLoading && !isError && tasks.length > 0 && viewMode === 'list' ? (
            <div className="overflow-hidden rounded-md border-2 border-[#7a5739] bg-white">
              <table className="min-w-full">
                <thead className="bg-[#fff6df] text-left text-xs font-black uppercase tracking-[0.16em] text-stone-700">
                  <tr>
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((task) => (
                    <TaskRow
                      key={task.assetId}
                      task={task}
                      isSelected={task.assetId === inspectorTaskId}
                      onSelect={handleSelectTask}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>

        <section className="rounded-md border-2 border-[#7a5739] bg-white/95 p-5 shadow-[6px_6px_0_rgba(80,48,24,0.18)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[#2f9b96]">Inspector</p>
              <h2 className="mt-1 text-xl font-black text-stone-950">Selected task details</h2>
            </div>
            {inspectorTask ? (
              <div className="flex shrink-0 flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => openEditTaskModal(inspectorTask)}
                  className="pixel-button bg-[#58b7b0] px-4 py-2 text-sm font-black text-white"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(inspectorTask)}
                  className="pixel-button bg-[#fff6df] px-4 py-2 text-sm font-black text-rose-700 hover:bg-rose-50"
                >
                  Delete
                </button>
              </div>
            ) : null}
          </div>

          <TaskInspector
            task={inspectorTask}
            inputPresets={inputPresets}
          />
        </section>
      </div>

      <TaskModal
        open={createOpen}
        mode="create"
        resetKey="task:create"
        initialValues={emptyTaskFormValues}
        inputPresets={inputPresets}
        availableTools={tools}
        availableToolCatalog={toolCatalog}
        taskOptions={tasks.map((task) => task.name)}
        isSubmitting={createTask.isPending || isPresetCatalogLoading}
        onClose={() => setCreateOpen(false)}
        onSubmit={handleCreate}
      />

      <TaskModal
        open={editTarget !== null}
        mode="edit"
        resetKey={editTarget ? `task:edit:${editTarget.assetId}:${editTarget.versionId}` : 'task:edit:closed'}
        initialValues={editTarget ? toFormValues(editTarget) : emptyTaskFormValues}
        inputPresets={inputPresets}
        availableTools={tools}
        availableToolCatalog={toolCatalog}
        taskOptions={tasks.map((task) => task.name)}
        isSubmitting={updateTask.isPending}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEdit}
      />

      <DeleteConfirm
        open={deleteTarget !== null}
        title="Delete task"
        message={deleteTarget ? `Delete ${deleteTarget.name}? This removes the task asset from the library.` : 'Delete this task?'}
        isPending={deleteTask.isPending}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
      />
    </PageFrame>
  );
}
