import { useState } from 'react';
import { PageFrame } from '../../components/layout/PageFrame';
import { PageHeader } from '../../components/platform/PageHeader';
import { readSelectedRunId, useFlowRunDetail } from './hooks';
import { RunSidebar } from '../../components/layout/Sidebar';
import { OutputPreview, RawJsonInspect } from './OutputPreview';

const tabs = [
  { value: 'output', label: 'Output Preview' },
  { value: 'input', label: 'Input' },
  { value: 'state', label: 'State' },
] as const;

type IOTab = (typeof tabs)[number]['value'];

export function IOPage() {
  const runId = readSelectedRunId();
  const { run, isLoading, error } = useFlowRunDetail(runId);
  const [tab, setTab] = useState<IOTab>('output');
  const activeTab = tabs.find((item) => item.value === tab) ?? tabs[0];
  const activeTabId = `run-io-${activeTab.value}-tab`;
  const activePanelId = `run-io-${activeTab.value}-panel`;

  return (
    <PageFrame sidebar={<RunSidebar />}>
      <PageHeader title="I/O" description="Inspect the selected workflow run input, output, and latest state snapshot." />

      {error ? <p className="mb-4 text-sm text-red-300">{error}</p> : null}
      {runId && isLoading ? <p className="text-sm text-stone-500">Loading selected run details.</p> : null}
      {!runId ? <p className="text-sm text-stone-500">Launch or select a run from the Run page.</p> : null}
      {runId && !isLoading && !error && !run ? <p className="text-sm text-stone-500">Selected run details are not available.</p> : null}

      {run ? (
        <div className="pixel-panel bg-[#fff6df] p-5">
          <div role="tablist" aria-label="Run I/O views" className="flex flex-wrap gap-2">
            {tabs.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                id={`run-io-${value}-tab`}
                role="tab"
                aria-selected={tab === value}
                aria-controls={`run-io-${value}-panel`}
                onClick={() => setTab(value)}
                className={`rounded-md border-2 px-3 py-2 text-sm font-black ${
                  tab === value ? 'border-[#2f9b96] bg-[#2f9b96] text-white' : 'border-[#7a5739] bg-[#fffaf0] text-stone-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div id={activePanelId} role="tabpanel" aria-labelledby={activeTabId} className="mt-4">
            {tab === 'output' ? <OutputPreview value={run.output_json} /> : null}
            {tab === 'input' ? <RawJsonInspect value={run.input_json} /> : null}
            {tab === 'state' ? <RawJsonInspect value={run.latest_state_snapshot?.state_json} /> : null}
          </div>
        </div>
      ) : null}
    </PageFrame>
  );
}
