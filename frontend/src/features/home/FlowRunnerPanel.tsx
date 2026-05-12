import { useEffect, useState } from 'react';
import { type PublishedFlowOption, usePublishedFlowOptions } from '../runs/hooks';

type FlowRunnerPanelProps = {
  onStartRequested: (flow: PublishedFlowOption) => void;
};

export function FlowRunnerPanel({ onStartRequested }: FlowRunnerPanelProps) {
  const { flows, isLoading, error } = usePublishedFlowOptions();
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && flows.length > 0) setSelected(flows[0].versionId);
  }, [flows, selected]);

  function handleRun() {
    if (!selected) return;
    const flow = flows.find((candidate) => candidate.versionId === selected);
    if (flow) onStartRequested(flow);
  }

  return (
    <aside className="w-80 shrink-0">
      <div className="rounded-md border-2 border-[#7a5739] bg-white/95 p-4 shadow-[4px_4px_0_rgba(80,48,24,0.18)]">
        <p className="text-xs font-black uppercase tracking-[0.16em] text-[#2f9b96]">Launcher</p>
        <h2 className="mb-3 mt-1 text-base font-black text-stone-950">Run a published Flow</h2>
        {isLoading ? (
          <p className="text-sm font-semibold text-stone-600">Loading flows...</p>
        ) : error ? (
          <p className="text-sm font-bold text-red-600">{String(error)}</p>
        ) : (
          <div className="flex flex-col gap-3">
            <label className="text-xs font-black uppercase tracking-[0.14em] text-stone-700">Select flow</label>
            <select
              className="rounded-md border-2 border-[#9a7a54] bg-[#fff6df] px-2 py-2 text-sm font-semibold text-stone-950 outline-none focus:border-[#2f9b96]"
              value={selected ?? ''}
              onChange={(event) => setSelected(event.target.value || null)}
            >
              <option value="">-- choose a flow --</option>
              {flows.map((flow) => (
                <option key={flow.versionId} value={flow.versionId}>
                  {flow.name} (v{flow.versionNo})
                </option>
              ))}
            </select>

            <button
              className="pixel-button mt-2 bg-[#ef8b2c] px-3 py-2 text-sm font-black text-white disabled:opacity-60"
              onClick={handleRun}
              disabled={!selected}
            >
              Start Flow
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

export default FlowRunnerPanel;
