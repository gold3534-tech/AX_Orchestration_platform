import type { TaskListItem } from './hooks';

type TaskCardProps = {
  task: TaskListItem;
  isSelected?: boolean;
  onSelect?: (task: TaskListItem) => void;
  onDetail?: (task: TaskListItem) => void;
};

export function TaskCard({ task, isSelected = false, onSelect, onDetail }: TaskCardProps) {
  function handleSelect() {
    if (onSelect) {
      onSelect(task);
      return;
    }

    onDetail?.(task);
  }

  return (
    <button
      type="button"
      onClick={handleSelect}
      className={`w-full rounded-md border-2 bg-[#fffaf0] p-4 text-left shadow-[4px_4px_0_rgba(80,48,24,0.20)] transition hover:-translate-y-0.5 hover:bg-[#fff3d1] ${
        isSelected ? 'border-[#2f9b96] ring-2 ring-[#58b7b0]/70' : 'border-[#9a7a54]'
      }`}
    >
      <h3 className="truncate text-xl font-black text-stone-950">{task.name}</h3>
      <p
        className="mt-3 overflow-hidden text-sm font-medium leading-6 text-stone-700"
        style={{
          display: '-webkit-box',
          WebkitBoxOrient: 'vertical',
          WebkitLineClamp: 3,
        }}
      >
        {task.description || 'No description has been written yet.'}
      </p>
    </button>
  );
}
