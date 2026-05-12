import { useEffect, useRef, useState } from 'react';

export type PendingHumanFeedbackRequest = {
  id: string;
  attempt_number?: number | null;
  prompt_json?: Record<string, unknown>;
};

type HumanFeedbackDialogProps = {
  pendingRequest: PendingHumanFeedbackRequest | null;
  isBusy: boolean;
  submitError: string | null;
  onSubmit: (outcome: 'approved' | 'needs_revision' | 'rejected', feedback: string) => Promise<void>;
};

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-3 text-xs text-stone-700">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

function numberValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function remainingRetriesFor(pendingRequest: PendingHumanFeedbackRequest | null) {
  const promptJson = pendingRequest?.prompt_json ?? {};
  const remainingRetries = numberValue(promptJson.remaining_retries);
  if (remainingRetries !== null) {
    return remainingRetries;
  }

  const maxAttempts = numberValue(promptJson.max_attempts);
  const attemptNumber = numberValue(promptJson.attempt_number ?? pendingRequest?.attempt_number);
  if (maxAttempts !== null && attemptNumber !== null) {
    return Math.max(maxAttempts - Math.max(attemptNumber - 1, 0), 0);
  }

  return null;
}

export function HumanFeedbackDialog({ pendingRequest, isBusy, submitError, onSubmit }: HumanFeedbackDialogProps) {
  const [feedback, setFeedback] = useState('');
  const [confirmApproveBeforeOutput, setConfirmApproveBeforeOutput] = useState(false);
  const hitlDialogRef = useRef<HTMLDivElement | null>(null);
  const promptJson = pendingRequest?.prompt_json ?? {};
  const requestMessage =
    typeof promptJson.message === 'string'
      ? promptJson.message
      : typeof promptJson.prompt === 'string'
        ? promptJson.prompt
        : 'HITL이 실행되었습니다. 계속 진행하시겠습니까?';
  const remainingRetries = remainingRetriesFor(pendingRequest);
  const retryExhausted = remainingRetries !== null && remainingRetries <= 0;
  const nextNodeId = typeof promptJson.next_node_id === 'string' ? promptJson.next_node_id : null;
  const isOutputNext = nextNodeId === 'output' || nextNodeId?.startsWith('output:') === true;

  useEffect(() => {
    setConfirmApproveBeforeOutput(false);
    setFeedback('');
  }, [pendingRequest?.id]);

  useEffect(() => {
    if (pendingRequest) {
      hitlDialogRef.current?.focus();
    }
  }, [pendingRequest?.id]);

  if (!pendingRequest) {
    return null;
  }

  async function submitHumanDecision(outcome: 'approved' | 'needs_revision' | 'rejected') {
    await onSubmit(outcome, feedback);
    setFeedback('');
    setConfirmApproveBeforeOutput(false);
  }

  async function handleFeedback(outcome: 'approved' | 'needs_revision' | 'rejected') {
    if (outcome === 'approved' && feedback.trim().length > 0 && isOutputNext) {
      setConfirmApproveBeforeOutput(true);
      return;
    }
    await submitHumanDecision(outcome);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#22170f]/50 px-4 py-6">
      <div
        ref={hitlDialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="hitl-dialog-title"
        tabIndex={-1}
        className="w-full max-w-xl rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[8px_8px_0_#7a5739]"
      >
        <h2 id="hitl-dialog-title" className="text-lg font-black text-[#22170f]">
          {requestMessage}
        </h2>
        <div className="mt-4">
          <JsonBlock value={promptJson.preview_payload ?? {}} />
        </div>
        <label className="mt-4 block text-sm font-medium text-stone-700">
          Feedback
          <textarea
            value={feedback}
            onChange={(event) => {
              setFeedback(event.target.value);
              setConfirmApproveBeforeOutput(false);
            }}
            rows={4}
            className="mt-2 w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-900"
          />
        </label>
        {retryExhausted ? <p className="mt-2 text-sm text-amber-700">최대 재시도 횟수를 초과했습니다.</p> : null}
        {confirmApproveBeforeOutput ? (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
            <p className="text-sm text-stone-900">
              피드백이 작성되었지만 다음으로 예정된 작업이 없습니다. 그래도 승인하시겠습니까?
            </p>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={() => submitHumanDecision('approved')}
                disabled={isBusy}
                className="pixel-button bg-[#2f9b96] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                Y
              </button>
              <button
                type="button"
                onClick={() => setConfirmApproveBeforeOutput(false)}
                disabled={isBusy}
                className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm font-bold text-[#22170f] disabled:opacity-50"
              >
                N
              </button>
            </div>
          </div>
        ) : null}
        {submitError ? <p className="mt-2 text-sm text-red-300">{submitError}</p> : null}
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => handleFeedback('approved')}
            disabled={isBusy}
            className="pixel-button bg-[#2f9b96] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            승인
          </button>
          <button
            type="button"
            onClick={() => handleFeedback('rejected')}
            disabled={isBusy}
            className="pixel-button bg-red-500 px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            거절
          </button>
          <button
            type="button"
            onClick={() => handleFeedback('needs_revision')}
            disabled={isBusy || retryExhausted}
            className="pixel-button bg-[#ef8b2c] px-3 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            재시도
          </button>
        </div>
      </div>
    </div>
  );
}
