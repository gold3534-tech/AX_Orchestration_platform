import { ErrorState } from '../../components/platform/ErrorState';
import { LoadingState } from '../../components/platform/LoadingState';
import type { TaskInputPresetEntry } from './hooks';

type TaskInputPresetPanelProps = {
  presets: TaskInputPresetEntry[];
  isLoading: boolean;
  error: unknown;
  onRefetch: () => Promise<unknown> | unknown;
};

export function TaskInputPresetPanel({ presets, isLoading, error, onRefetch }: TaskInputPresetPanelProps) {
  return (
    <section className="pixel-panel bg-[#fff6df] p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Template settings</p>
          <h2 className="mt-1 text-xl font-black text-[#22170f]">Input presets</h2>
          <p className="mt-2 text-sm text-stone-600">
            태스크 본문에서 사용할 파라미터 preset catalog를 확인합니다. 관리는 backend seed와 migration에서 처리합니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            void onRefetch();
          }}
          className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-xs font-bold text-[#22170f]"
        >
          새로고침
        </button>
      </div>

      <div className="mt-5">
        {isLoading ? <LoadingState /> : null}
        {!isLoading && error ? (
          <ErrorState message={`Unable to load input presets: ${error instanceof Error ? error.message : 'Unknown error'}`} />
        ) : null}
        {!isLoading && !error && presets.length === 0 ? (
          <div className="rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] p-4 text-sm text-stone-600">
            아직 등록된 input preset이 없습니다.
          </div>
        ) : null}
        {!isLoading && !error && presets.length > 0 ? (
          <div className="space-y-3">
            {presets.map((preset) => (
              <div key={preset.id} className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4 shadow-[3px_3px_0_rgba(122,87,57,0.35)]">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="text-sm font-black text-[#22170f]">{preset.label}</p>
                    <p className="text-xs text-stone-500">
                      {preset.key} · {preset.inputType} · order {preset.sortOrder}
                    </p>
                    {preset.description ? <p className="text-xs text-stone-500">{preset.description}</p> : null}
                  </div>
                  <span className="rounded border border-[#7a5739]/50 px-3 py-1.5 text-xs font-bold text-stone-600">
                    {preset.isActive ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
