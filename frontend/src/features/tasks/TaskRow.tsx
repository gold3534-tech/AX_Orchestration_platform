import type { TaskListItem } from './hooks';

type TaskRowProps = {
  task: TaskListItem;
  isSelected?: boolean;
  onSelect?: (task: TaskListItem) => void;
  onDetail?: (task: TaskListItem) => void;
};

export function TaskRow({ task, isSelected = false, onSelect, onDetail }: TaskRowProps) {
  function handleSelect() {
    if (onSelect) {
      onSelect(task);
      return;
    }

    onDetail?.(task);
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
      className={`cursor-pointer border-b-2 border-[#d7b98b] transition last:border-b-0 hover:bg-[#fff3d1] ${
        isSelected ? 'bg-[#d7f1ee] ring-2 ring-inset ring-[#2f9b96]' : ''
      }`}
    >
      <td className="px-4 py-4">
        <p className="max-w-56 truncate text-base font-black text-stone-950">{task.name}</p>
      </td>
      <td className="px-4 py-4">
        <p
          className="max-w-xl overflow-hidden text-sm font-medium leading-6 text-stone-700"
          style={{
            display: '-webkit-box',
            WebkitBoxOrient: 'vertical',
            WebkitLineClamp: 2,
          }}
        >
          {task.description || 'No description has been written yet.'}
        </p>
      </td>
    </tr>
  );
}
