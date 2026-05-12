import type { CrewListItem } from './hooks';

type CrewCardProps = {
  crew: CrewListItem;
  isSelected?: boolean;
  onSelect?: (crew: CrewListItem) => void;
  onDetail?: (crew: CrewListItem) => void;
};

export function CrewCard({ crew, isSelected = false, onSelect, onDetail }: CrewCardProps) {
  function handleSelect() {
    if (onSelect) {
      onSelect(crew);
      return;
    }

    onDetail?.(crew);
  }

  return (
    <button
      type="button"
      onClick={handleSelect}
      className={`block w-full overflow-hidden rounded-md border-2 bg-[#fffaf0] px-4 py-3 text-left shadow-[4px_4px_0_#7a5739] transition hover:bg-[#ffe6b3] ${
        isSelected ? 'border-[#2f9b96] ring-2 ring-[#2f9b96] ring-offset-2 ring-offset-[#f3dfbd]' : 'border-[#7a5739]'
      }`}
    >
      <div className="flex w-full items-start justify-between gap-3">
        <h3 className="min-w-0 truncate text-base font-black text-[#22170f]">{crew.name}</h3>
        <span
          className={`shrink-0 rounded border px-2.5 py-1 text-xs font-bold ${
            crew.status === 'published'
              ? 'border-[#2f9b96] bg-[#e6f6f2] text-emerald-800'
              : crew.status.toLowerCase() === 'draft'
                ? 'border-[#ef8b2c] bg-[#ffe6b3] text-amber-800'
                : 'border-[#7a5739]/40 bg-[#f8e8c8] text-stone-700'
          }`}
        >
          {crew.status}
        </span>
      </div>
      <p className="mt-2 line-clamp-2 break-words text-sm leading-6 text-stone-600">
        {crew.description || 'No summary has been written yet.'}
      </p>
    </button>
  );
}
