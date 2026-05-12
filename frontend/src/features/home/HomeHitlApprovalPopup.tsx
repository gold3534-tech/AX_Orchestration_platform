import { useEffect, useState } from 'react';
import { Check, FileText, X } from 'lucide-react';
import { OutputPreview } from '../runs/OutputPreview';
import type { PendingHumanFeedbackRequest } from '../runs/HumanFeedbackDialog';

type HomeHitlApprovalPopupProps = {
  pendingRequest: PendingHumanFeedbackRequest | null;
  isBusy: boolean;
  submitError: string | null;
  onSubmit: (outcome: 'approved' | 'rejected', feedback: string) => Promise<void>;
};

function stringValue(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function compactPreview(value: unknown) {
  if (value === null || value === undefined) return {};
  return value;
}

export function HomeHitlApprovalPopup({ pendingRequest, isBusy, submitError, onSubmit }: HomeHitlApprovalPopupProps) {
  const [feedback, setFeedback] = useState('');
  const promptJson = pendingRequest?.prompt_json ?? {};
  const message =
    stringValue(promptJson, 'message') ?? stringValue(promptJson, 'prompt') ?? 'Human approval is requested.';
  const preview = compactPreview(promptJson.preview_payload ?? promptJson.output ?? promptJson);
  const sourceNodeId = stringValue(promptJson, 'source_node_id') ?? '-';
  const nextNodeId = stringValue(promptJson, 'next_node_id') ?? '-';

  useEffect(() => {
    setFeedback('');
  }, [pendingRequest?.id]);

  if (!pendingRequest) return null;

  async function submit(outcome: 'approved' | 'rejected') {
    await onSubmit(outcome, feedback);
    setFeedback('');
  }

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-stone-950/45 px-4 py-5">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="home-hitl-title"
        className="max-h-[92%] w-full max-w-5xl overflow-hidden border-[7px] border-[#4d2b1c] bg-[#fff1c8] shadow-[0_0_0_4px_#1a0f0a,0_10px_0_#2d170f]"
      >
        <div className="border-[5px] border-[#d6a85e] bg-[#fff8dd]">
          <div className="flex flex-wrap items-center justify-center gap-5 border-b-4 border-dotted border-[#c99d58] px-6 py-5 text-center">
            <div className="grid h-20 w-20 place-items-center border-4 border-[#4d2b1c] bg-[#e8f0e8] text-4xl shadow-[inset_-4px_-4px_0_#b7c7bd]">
              <FileText className="h-12 w-12 text-[#4d2b1c]" strokeWidth={3} />
            </div>
            <h2 id="home-hitl-title" className="font-mono text-5xl font-black tracking-wide text-[#4d2b1c]">
              결재 서류
            </h2>
            <div className="-rotate-3 border-4 border-[#d44d27] px-4 py-2 font-mono text-2xl font-black text-[#d44d27]">
              결재 대기
            </div>
          </div>

          <div className="grid max-h-[62vh] gap-4 overflow-auto p-5 lg:grid-cols-[1fr_0.92fr]">
            <div className="space-y-4">
              <div className="grid border-2 border-[#d2a15b] bg-[#fff7dc] font-mono text-stone-950">
                {[
                  ['문서번호', pendingRequest.id],
                  ['요청 노드', sourceNodeId],
                  ['다음 노드', nextNodeId],
                  ['상태', '승인 대기'],
                ].map(([label, value]) => (
                  <div key={label} className="grid grid-cols-[10rem_1fr] border-b border-dashed border-[#d2a15b] last:border-b-0">
                    <div className="bg-[#fff0c2] px-4 py-3 font-black">{label}</div>
                    <div className="min-w-0 px-4 py-3 font-bold">{value}</div>
                  </div>
                ))}
              </div>

              <div className="border-2 border-[#d2a15b] bg-[#fff7dc] p-4">
                <p className="mb-2 font-mono text-lg font-black text-[#4d2b1c]">요청 내용</p>
                <p className="whitespace-pre-wrap text-sm leading-6 text-stone-900">{message}</p>
              </div>

              <label className="block border-2 border-[#d2a15b] bg-[#fff7dc] p-4">
                <span className="font-mono text-lg font-black text-[#4d2b1c]">비고</span>
                <textarea
                  value={feedback}
                  onChange={(event) => setFeedback(event.target.value)}
                  rows={3}
                  className="mt-2 w-full resize-none border-2 border-[#d2a15b] bg-[#fffdf1] px-3 py-2 text-sm text-stone-950 outline-none focus:border-[#1f8b83]"
                  placeholder="승인 또는 반려 사유를 입력하세요."
                />
              </label>
            </div>

            <div className="space-y-4">
              <div className="border-2 border-[#d2a15b] bg-[#fff7dc] p-4">
                <div className="mb-3 inline-block border-4 border-[#4d2b1c] bg-[#1f8b83] px-4 py-1 font-mono text-lg font-black text-white">
                  검토 대상
                </div>
                <div className="max-h-72 overflow-auto border border-[#d2a15b] bg-[#fffdf1] p-3 text-sm">
                  <OutputPreview value={preview} />
                </div>
              </div>

              {submitError ? (
                <div className="border-2 border-[#b53a22] bg-[#ffe0d2] px-4 py-3 font-mono text-sm font-bold text-[#8f2d19]">
                  {submitError}
                </div>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap justify-center gap-4 border-t-4 border-[#d2a15b] bg-[#fff0c2] px-5 py-5">
            <button
              type="button"
              onClick={() => submit('approved')}
              disabled={isBusy}
              className="inline-flex items-center gap-3 border-4 border-[#4d2b1c] bg-[#1f8b83] px-12 py-3 font-mono text-2xl font-black text-white shadow-[inset_-5px_-5px_0_#12635d] disabled:opacity-60"
            >
              <Check className="h-7 w-7" strokeWidth={4} />
              승인
            </button>
            <button
              type="button"
              onClick={() => submit('rejected')}
              disabled={isBusy}
              className="inline-flex items-center gap-3 border-4 border-[#4d2b1c] bg-[#df542d] px-12 py-3 font-mono text-2xl font-black text-white shadow-[inset_-5px_-5px_0_#9f321b] disabled:opacity-60"
            >
              <X className="h-7 w-7" strokeWidth={4} />
              반려
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
