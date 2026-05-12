import type { ReactNode } from 'react';
import type { AgentListItem } from './hooks';

type AgentRowProps = {
  agent: AgentListItem;
  photoSlot?: ReactNode;
  summary?: string;
  isSelected?: boolean;
  onSelect?: (agent: AgentListItem) => void;
  onDetail?: (agent: AgentListItem) => void;
  onEdit?: (agent: AgentListItem) => void;
  onDelete?: (agent: AgentListItem) => void;
};

function getGoal(agent: AgentListItem, summary?: string) {
  return summary || agent.goal || 'No goal has been written yet.';
}

function AgentPhoto({ agent }: { agent: AgentListItem }) {
  if (agent.photoUrl) {
    return <img src={agent.photoUrl} alt="" className="h-16 w-16 rounded-sm border-2 border-[#9a7a54] object-cover" loading="lazy" />;
  }

  return (
    <div className="flex h-16 w-16 items-center justify-center rounded-sm border-2 border-[#9a7a54] bg-[#efe8ff] text-[#6f4bd9]">
      <span className="font-ax-label text-xs font-semibold uppercase tracking-[0.16em]">Photo</span>
    </div>
  );
}

export function AgentRow({ agent, photoSlot, summary, isSelected = false, onSelect, onDetail }: AgentRowProps) {
  function handleSelect() {
    if (onSelect) {
      onSelect(agent);
      return;
    }

    onDetail?.(agent);
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
      className={`font-ax-body cursor-pointer border-b-2 border-[#d7b98b] transition last:border-b-0 hover:bg-[#fff3d1] ${
        isSelected ? 'bg-[#d7f1ee] ring-2 ring-inset ring-[#2f9b96]' : ''
      }`}
    >
      <td className="px-4 py-4">
        <section aria-label="Photo">{photoSlot ?? <AgentPhoto agent={agent} />}</section>
      </td>
      <td className="px-4 py-4">
        <p className="max-w-48 truncate text-base font-black text-stone-950">{agent.name}</p>
        <p className="mt-1 max-w-48 truncate text-sm font-semibold text-stone-700">{agent.role || 'Role not set'}</p>
      </td>
      <td className="px-4 py-4">
        <p
          className="max-w-sm overflow-hidden text-sm leading-6 text-stone-700"
          style={{
            display: '-webkit-box',
            WebkitBoxOrient: 'vertical',
            WebkitLineClamp: 2,
          }}
        >
          {getGoal(agent, summary)}
        </p>
      </td>
    </tr>
  );
}
