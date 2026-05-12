import { NavLink } from 'react-router-dom';

export type SidebarItem = {
  label: string;
  to: string;
  end?: boolean;
};

type SidebarProps = {
  title: string;
  items: readonly SidebarItem[];
  ariaLabel?: string;
};

export function GenericSidebar({ title, items, ariaLabel }: SidebarProps) {
  return (
    <nav aria-label={ariaLabel || `${title} sections`} className="w-44 shrink-0 border-r-2 border-[#7a5739] bg-[#fff6df]/55 p-3 2xl:w-52 2xl:p-4">
      <p className="mb-3 text-[11px] font-black uppercase tracking-[0.22em] text-stone-950">{title}</p>
      <div className="flex flex-col gap-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              [
                'rounded-md border-2 px-3 py-2 text-sm font-semibold transition',
                isActive
                  ? 'border-[#5b3424] bg-[#58b7b0] text-white shadow-[3px_3px_0_rgba(80,48,24,0.22)]'
                  : 'border-transparent text-stone-950 hover:border-[#7a5739] hover:bg-[#ffe6b9]',
              ].join(' ')
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

const buildSections = [
  { label: 'Agents', to: '/build/agents' },
  { label: 'Tasks', to: '/build/tasks' },
  { label: 'Crews', to: '/build/crews' },
  { label: 'Flows', to: '/build/flows' },
  { label: 'Tools', to: '/build/tools' },
  { label: 'Credentials', to: '/build/credentials' },
  { label: 'Knowledge', to: '/build/knowledge' },
  { label: 'Settings', to: '/build/settings' },
] as const;

export function Sidebar() {
  return <GenericSidebar title="Build" items={buildSections} />;
}

const runSections = [
  { label: 'Run', to: '/run', end: true },
  { label: 'Streaming', to: '/run/streaming' },
  { label: 'I/O', to: '/run/io' },
] as const;

export function RunSidebar() {
  return <GenericSidebar title="Run" items={runSections} />;
}
