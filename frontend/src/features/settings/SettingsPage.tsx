import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { PageHeader } from '../../components/platform/PageHeader';
import { TaskInputPresetPanel } from './TaskInputPresetPanel';
import { useSettingsShell } from './hooks';

export function SettingsPage() {
  const {
    taskInputPresets,
    isTaskInputPresetsLoading,
    taskInputPresetsError,
    refetchTaskInputPresets,
  } = useSettingsShell();

  return (
    <PageFrame sidebar={<Sidebar />}>
      <PageHeader
        title="Settings"
        description="Input presets and non-secret runtime setup. Provider API keys now live on the Credentials page."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(280px,0.9fr)]">
        <div className="space-y-6">
          <TaskInputPresetPanel
            presets={taskInputPresets}
            isLoading={isTaskInputPresetsLoading}
            error={taskInputPresetsError}
            onRefetch={refetchTaskInputPresets}
          />
        </div>

        <aside className="pixel-panel bg-[#fff6df] p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Runtime focus</p>
          <h2 className="mt-1 text-xl font-black text-[#22170f]">Build settings stay execution-oriented</h2>
          <p className="mt-2 text-sm text-stone-600">
            Provider API keys are managed on the Credentials page. This settings page keeps non-secret runtime setup
            visible.
          </p>
          <div className="mt-4 space-y-3 text-sm text-stone-600">
            <p>Profile preferences will live elsewhere.</p>
            <p>Input presets are shown as a backend-managed catalog.</p>
            <p>Credential connection state is intentionally separated from general settings.</p>
          </div>
        </aside>
      </div>
    </PageFrame>
  );
}
