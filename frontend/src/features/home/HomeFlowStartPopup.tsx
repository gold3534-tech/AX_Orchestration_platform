import { useEffect, useState } from 'react';
import type { PublishedFlowOption } from '../runs/hooks';

type HomeFlowStartPopupProps = {
  flow: PublishedFlowOption;
  isBusy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onStart: (inputs: Record<string, unknown>) => Promise<void>;
};

export function HomeFlowStartPopup({ flow, isBusy = false, error = null, onCancel, onStart }: HomeFlowStartPopupProps) {
  const [topic, setTopic] = useState('');

  useEffect(() => {
    setTopic('');
  }, [flow.versionId]);

  async function handleSubmit() {
    await onStart(flow.hasInputNode ? { topic } : {});
  }

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-stone-950/35 px-4 py-6">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="home-flow-start-title"
        className="relative w-full max-w-[480px] rounded-md border-[5px] border-[#5b3424] bg-[#f4d9a6] p-4 text-stone-950 shadow-2xl"
      >
        <div className="absolute left-1/2 top-0 h-7 w-40 -translate-x-1/2 -translate-y-1/2 rounded-sm border-[3px] border-[#2b332e] bg-[#58b7b0] shadow-[inset_0_-4px_0_#2d7772]" />
        <div className="rounded-sm border-2 border-[#8a6145] bg-[#ffe6b9] px-4 py-5 shadow-[inset_0_0_0_2px_#f8d99d]">
          <h2 id="home-flow-start-title" className="text-center text-2xl font-black tracking-wide">
            업무 의뢰서
          </h2>
          <div className="my-4 h-1 bg-[#6f442c]" />

          <div className="grid gap-3">
            <section className="grid gap-2 border-b-2 border-[#c79d67] pb-3">
              <p className="text-base font-black">요청 제목</p>
              <div className="rounded-sm border-2 border-[#8a6145] bg-white/80 px-3 py-2 text-sm font-semibold">
                {flow.name} v{flow.versionNo}
              </div>
            </section>

            <section className="grid gap-2 border-b-2 border-[#c79d67] pb-3">
              <p className="text-base font-black">작업 목표</p>
              <div className="min-h-20 rounded-sm border-2 border-[#8a6145] bg-white/80 px-3 py-2 text-sm leading-6">
                {flow.description?.trim() || '등록된 요약이 없습니다.'}
              </div>
            </section>

            {flow.hasInputNode ? (
              <section className="grid gap-2 border-b-2 border-[#c79d67] pb-3">
                <label htmlFor="home-flow-topic" className="text-lg font-black">
                  키워드
                </label>
                <textarea
                  id="home-flow-topic"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                  rows={2}
                  className="w-full resize-none rounded-sm border-2 border-[#8a6145] bg-white/90 px-3 py-2 text-sm outline-none focus:border-[#2f8f89]"
                  placeholder="이번 실행에 전달할 키워드나 주제를 입력하세요."
                />
              </section>
            ) : (
              <section className="border-b-2 border-[#c79d67] pb-3 text-sm font-semibold text-stone-700">
                이 Flow에는 Input Node가 없어 추가 입력 없이 시작합니다.
              </section>
            )}

            {error ? <p className="text-sm font-semibold text-red-700">{error}</p> : null}
          </div>
        </div>

        <div className="mt-4 flex justify-center gap-5">
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="min-w-24 rounded-md border-[3px] border-[#164b4a] bg-[#2f9b96] px-4 py-2 text-base font-black text-white shadow-[0_4px_0_#123b3a] disabled:opacity-60"
          >
            취소
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isBusy}
            className="min-w-28 rounded-md border-[3px] border-[#8a431f] bg-[#ef8b2c] px-4 py-2 text-base font-black text-white shadow-[0_4px_0_#5f2c17] disabled:opacity-60"
          >
            {isBusy ? '시작 중...' : '시작하기'}
          </button>
        </div>
      </div>
    </div>
  );
}
