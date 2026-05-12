import type { ReactNode } from 'react';
import type { AgentListItem } from './hooks';

type AgentCardProps = {
  agent: AgentListItem;
  photoSlot?: ReactNode;
  isSelected?: boolean;
  onSelect?: (agent: AgentListItem) => void;
  onDetail?: (agent: AgentListItem) => void;
  onEdit?: (agent: AgentListItem) => void;
  onDelete?: (agent: AgentListItem) => void;
};

function AgentPhoto({ agent }: { agent: AgentListItem }) {
  if (agent.photoUrl) {
    return (
      <img
        src={agent.photoUrl}
        alt=""
        className="h-full w-full rounded-sm object-cover"
        loading="lazy"
      />
    );
  }

  return (
    <div className="flex h-full w-full flex-col items-center justify-center rounded-sm border-2 border-[#9a7a54] bg-[#efe8ff] px-2 text-center text-[#6f4bd9]">
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="mb-1.5 h-7 w-7"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="10" cy="7" r="4" />
        <path d="M20 8v6" />
        <path d="M23 11h-6" />
      </svg>
      <span className="font-ax-label text-xs font-semibold uppercase tracking-[0.16em]">Photo</span>
    </div>
  );
}

export function AgentCard({
  agent,
  photoSlot,
  isSelected = false,
  onSelect,
  onDetail,
}: AgentCardProps) {
  function handleSelect() {
    if (onSelect) {
      onSelect(agent);
      return;
    }

    onDetail?.(agent);
  }

  return (
    <button
      type="button"
      onClick={handleSelect}
      className={`font-ax-body h-36 w-full rounded-md border-2 bg-[#fffaf0] p-3 text-left shadow-[4px_4px_0_rgba(80,48,24,0.20)] transition hover:-translate-y-0.5 hover:bg-[#fff3d1] ${
        isSelected ? 'border-[#2f9b96] ring-2 ring-[#58b7b0]/70' : 'border-[#9a7a54]'
      }`}
    >
      <div className="grid h-full grid-cols-[30%_minmax(0,1fr)] gap-4">
        <section aria-label="Photo" className="min-h-0 rounded-md border-2 border-[#d7b98b] bg-[#fff6df] p-1">
          {photoSlot ?? <AgentPhoto agent={agent} />}
        </section>

        <div className="flex min-w-0 flex-col justify-center">
          <h3 className="truncate text-lg font-black text-stone-950">{agent.name}</h3>
          <p className="mt-1.5 truncate text-sm font-semibold text-stone-700">{agent.role || 'Role not set'}</p>
        </div>
      </div>
    </button>
  );
}
