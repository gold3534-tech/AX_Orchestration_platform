import { OutputPreview } from '../runs/OutputPreview';

type HomeResultReportPopupProps = {
  output: unknown;
  hasWarning: boolean;
  onClose: () => void;
};

export function HomeResultReportPopup({ output, hasWarning, onClose }: HomeResultReportPopupProps) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-stone-950/35 px-4">
      <section className="max-h-[88%] w-full max-w-2xl overflow-hidden border-4 border-[#5b321f] bg-[#f8e7bd] shadow-[0_0_0_4px_#1f8b83,0_0_0_8px_#5b321f]">
        <div className="flex items-center justify-between border-b-4 border-[#5b321f] bg-[#fff4cf] px-5 py-4">
          <div>
            <p className="text-xs font-black uppercase tracking-wide text-[#1f8b83]">Final Output</p>
            <h2 className="font-mono text-2xl font-black text-stone-950">RESULT REPORT</h2>
          </div>
          <div className="grid h-12 w-12 place-items-center border-4 border-[#5b321f] bg-[#45c486] font-mono text-xl font-black text-stone-950">
            OK
          </div>
        </div>

        {hasWarning ? (
          <div className="border-b-4 border-[#5b321f] bg-[#ffcf7a] px-5 py-2 font-mono text-sm font-bold text-[#6d2b18]">
            Warning: an intermediate LLM response could not be parsed.
          </div>
        ) : null}

        <div className="max-h-[58vh] overflow-auto bg-[#fff4cf] p-5">
          <OutputPreview value={output} />
        </div>

        <div className="flex justify-end gap-3 border-t-4 border-[#5b321f] bg-[#f8e7bd] px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="border-4 border-[#5b321f] bg-[#ec6f32] px-6 py-2 font-mono text-lg font-black text-white shadow-[inset_-3px_-3px_0_#9f3d1f]"
          >
            Close
          </button>
        </div>
      </section>
    </div>
  );
}
