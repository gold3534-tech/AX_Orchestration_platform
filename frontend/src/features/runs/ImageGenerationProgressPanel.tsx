import type { ImageProgressGroup, ImageProgressSlot } from './imageProgressModel';

type ImageGenerationProgressPanelProps = {
  groups: ImageProgressGroup[];
};

function formatElapsed(ms: number | undefined) {
  if (ms === undefined) return null;
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`;
}

function statusClassName(status: ImageProgressSlot['status']) {
  if (status === 'completed') return 'border-emerald-200 bg-emerald-50 text-emerald-800';
  if (status === 'failed') return 'border-red-200 bg-red-50 text-red-800';
  return 'border-[#2f9b96] bg-[#e6f6f2] text-[#14645f]';
}

function statusLabel(status: ImageProgressSlot['status']) {
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Failed';
  return 'Generating';
}

function SlotCard({ slot }: { slot: ImageProgressSlot }) {
  const elapsed = formatElapsed(slot.elapsedMs);
  const isLongRunning = slot.status === 'generating' && (slot.elapsedMs ?? 0) > 120000;

  return (
    <article className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-stone-900">Slide {slot.index + 1}</h4>
        <span className={`rounded border px-2 py-0.5 text-xs font-bold ${statusClassName(slot.status)}`}>
          {statusLabel(slot.status)}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-stone-500">
        {elapsed ? <span>{elapsed}</span> : null}
        {slot.mimeType ? <span>{slot.mimeType}</span> : null}
        {slot.retryable ? (
          <span className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 font-bold text-amber-800">
            Retryable
          </span>
        ) : null}
        {isLongRunning ? <span className="font-semibold text-amber-700">Taking longer than usual</span> : null}
      </div>

      {slot.promptPreview ? <p className="mt-2 line-clamp-3 text-sm text-stone-700">{slot.promptPreview}</p> : null}

      {slot.artifactId ? (
        <p className="mt-2 break-words text-xs text-stone-500">
          Artifact:{' '}
          {slot.previewUrl ? (
            <a
              href={slot.previewUrl}
              className="font-semibold text-cyan-700 underline decoration-cyan-300 underline-offset-2"
            >
              Open artifact {slot.artifactId}
            </a>
          ) : (
            <span className="font-semibold text-stone-700">{slot.artifactId}</span>
          )}
        </p>
      ) : null}

      {slot.errorMessage ? (
        <p className="mt-2 whitespace-pre-wrap break-words text-sm font-medium text-red-700">{slot.errorMessage}</p>
      ) : null}
      {slot.rawError && slot.rawError !== slot.errorMessage ? (
        <p className="mt-1 whitespace-pre-wrap break-words text-xs text-red-500">{slot.rawError}</p>
      ) : null}
    </article>
  );
}

export function ImageGenerationProgressPanel({ groups }: ImageGenerationProgressPanelProps) {
  if (groups.length === 0) return null;

  return (
    <section className="pixel-panel bg-[#fff6df] p-5">
      <div className="mb-4">
        <p className="text-xs font-semibold uppercase text-[#2f9b96]">Images</p>
        <h2 className="mt-1 text-xl font-black text-[#22170f]">Image generation progress</h2>
      </div>

      <div className="space-y-4">
        {groups.map((group) => (
          <div key={group.groupId}>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-stone-900">{group.nodeId ?? group.taskId ?? group.groupId}</p>
                {group.taskId && group.taskId !== group.nodeId ? (
                  <p className="mt-1 text-xs text-stone-500">Task: {group.taskId}</p>
                ) : null}
              </div>
              <p className="text-sm font-semibold text-stone-700">
                {group.completedCount} / {group.totalCount} images complete
              </p>
            </div>

            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {group.slots.map((slot) => (
                <SlotCard key={`${group.groupId}-${slot.index}`} slot={slot} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
