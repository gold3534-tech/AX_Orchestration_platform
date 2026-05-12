import { Outlet } from 'react-router-dom';
import { TopTabs } from './TopTabs';

export function AppShell() {
  return (
    <div role="application" aria-label="AI Oh Frontend" className="flex min-h-screen flex-col bg-[#f3dfbd] text-stone-950">
      <TopTabs />
      <div className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </div>
    </div>
  );
}
