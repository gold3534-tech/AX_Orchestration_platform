import { NavLink } from 'react-router-dom';

const tabs = [
  { label: 'Home', to: '/home' },
  { label: 'Build', to: '/build' },
  { label: 'Run', to: '/run' },
] as const;

export function TopTabs() {
  return (
    <nav aria-label="Primary tabs" className="border-b-2 border-[#7a5739] bg-[#f3dfbd]/95 px-6 py-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex gap-2">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              role="tab"
              className={({ isActive }) =>
                [
                  'pixel-button px-4 py-2 text-sm font-black transition',
                  isActive ? 'bg-[#ef8b2c] text-white' : 'bg-[#fff6df] text-stone-950 hover:bg-[#ffe6b9]',
                ].join(' ')
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </div>
        <NavLink
          to="/login"
          className="pixel-button bg-[#fff6df] px-4 py-2 text-sm font-black text-stone-950 transition hover:bg-[#ffe6b9]"
        >
          Login
        </NavLink>
      </div>
    </nav>
  );
}
