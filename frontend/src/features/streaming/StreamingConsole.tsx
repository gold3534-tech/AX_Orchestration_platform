import { FormEvent, useState } from 'react';
import type { SceneLogLine } from './streamingTypes';

type StreamingConsoleProps = {
  logs: SceneLogLine[];
  isWaitingForHuman: boolean;
  requestId: string | null;
  isSubmitting: boolean;
  submitError: string | null;
  onSubmitFeedback: (feedback: string) => Promise<void>;
};

function formatTime(timestamp: string) {
  if (!timestamp) return '--:--:--';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function StreamingConsole({
  logs,
  isWaitingForHuman,
  requestId,
  isSubmitting,
  submitError,
  onSubmitFeedback,
}: StreamingConsoleProps) {
  const [feedback, setFeedback] = useState('');

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = feedback.trim();
    if (!value || !requestId) return;
    await onSubmitFeedback(value);
    setFeedback('');
  }

  return (
    <section className="overflow-hidden rounded-md border border-[#5b735d] bg-[#d8e0ce] font-mono shadow-[0_14px_34px_rgba(46,61,43,0.2)]">
      <div className="flex items-center justify-between border-b border-[#5b735d] bg-[#91a981] px-3 py-2 text-xs font-bold uppercase text-[#1f2c1f]">
        <span>System Logs & Communications</span>
        <span>{isWaitingForHuman ? 'HITL waiting' : 'Live stream'}</span>
      </div>
      <div className="h-48 overflow-auto bg-[#082011] px-4 py-3 text-sm leading-6 text-[#b9f7a8]">
        {logs.length === 0 ? <p className="text-[#76a86c]">[SYSTEM] Waiting for workflow telemetry...</p> : null}
        {logs.map((log) => (
          <p key={log.id} className={log.level === 'error' ? 'text-[#ff9c90]' : log.level === 'hitl' ? 'text-[#f7e68f]' : undefined}>
            [{log.source.toUpperCase()}] {formatTime(log.timestamp)} {log.message}
          </p>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-[#5b735d] bg-[#e8eee2] p-2">
        <input
          className="min-w-0 flex-1 rounded border border-[#9aa88f] bg-[#f6faf2] px-3 py-2 text-sm text-[#1f2c1f] outline-none focus:border-[#6c7fd8]"
          value={feedback}
          onChange={(event) => setFeedback(event.target.value)}
          disabled={!requestId || isSubmitting}
          placeholder={isWaitingForHuman ? 'Enter HITL feedback or approval note...' : 'HITL input will activate when feedback is requested.'}
          aria-label="Human feedback message"
        />
        <button
          type="submit"
          disabled={!requestId || !feedback.trim() || isSubmitting}
          className="rounded border border-[#343d2f] bg-[#2f3d2f] px-4 py-2 text-sm font-semibold text-[#f2f7ec] disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
      {submitError ? <p className="border-t border-[#d7a09b] bg-[#ffe5e1] px-3 py-2 text-sm text-[#8b2921]">{submitError}</p> : null}
    </section>
  );
}
