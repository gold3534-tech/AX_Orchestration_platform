import type { CrewListItem } from './hooks';

type CrewRowProps = {
  crew: CrewListItem;
  isSelected?: boolean;
  onSelect?: (crew: CrewListItem) => void;
  onDetail?: (crew: CrewListItem) => void;
};

export function CrewRow({ crew, isSelected = false, onSelect, onDetail }: CrewRowProps) {
  function handleSelect() {
    if (onSelect) {
      onSelect(crew);
      return;
    }

    onDetail?.(crew);
  }

  return (
    <tr
      tabIndex={0}
      onClick={handleSelect}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          handleSelect();
        }
      }}
      className={`cursor-pointer border-b border-[#7a5739]/30 transition last:border-b-0 hover:bg-[#ffe6b3] ${
        isSelected ? 'bg-[#e6f6f2] ring-2 ring-inset ring-[#2f9b96]' : ''
      }`}
    >
      <td className="px-4 py-4">
        <div className="flex items-center gap-2">
          <p className="max-w-48 truncate text-sm font-black text-[#22170f]">{crew.name}</p>
          <span className="rounded border border-[#7a5739]/40 bg-[#f8e8c8] px-2 py-0.5 text-[11px] font-bold text-stone-600">
            {crew.status}
          </span>
        </div>
      </td>
      <td className="px-4 py-4">
        <p
          className="max-w-xl overflow-hidden text-sm leading-6 text-stone-700"
          style={{
            display: '-webkit-box',
            WebkitBoxOrient: 'vertical',
            WebkitLineClamp: 2,
          }}
        >
          {crew.description || 'No summary has been written yet.'}
        </p>
      </td>
    </tr>
  );
}
