import { NavLink } from 'react-router-dom';

type RunSection = {
  label: string;
  to: string;
  end?: boolean;
};

const runSections: RunSection[] = [
  { label: 'Run', to: '/run', end: true },
  { label: 'Streaming', to: '/run/streaming' },
  { label: 'I/O', to: '/run/io' },
] as const;

export function RunSidebar() {
  return (
    <nav aria-label="Run sections" className="w-44 shrink-0 border-r-2 border-[#7a5739] bg-[#f8e8c8]/75 p-3 2xl:w-52 2xl:p-4">
      <p className="mb-3 text-[11px] font-black uppercase tracking-[0.22em] text-[#5b3424]">Run</p>
      <div className="flex flex-col gap-1">
        {runSections.map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            end={section.end}
            className={({ isActive }) =>
              [
                'rounded-md border-2 px-3 py-2 text-sm font-bold transition',
                isActive
                  ? 'border-[#5b3424] bg-[#2f9b96] text-white'
                  : 'border-transparent text-stone-800 hover:border-[#7a5739] hover:bg-[#ffe6b3] hover:text-stone-950',
              ].join(' ')
            }
          >
            {section.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
