import { type ReactNode } from 'react';

type PageFrameProps = {
  children: ReactNode;
  sidebar?: ReactNode;
};

export function PageFrame({ children, sidebar }: PageFrameProps) {
  return (
    <div className="flex min-h-0 flex-1 overflow-hidden">
      {sidebar ? sidebar : null}
      <main className="min-w-0 flex-1 overflow-auto bg-transparent px-5 py-5 2xl:px-6 2xl:py-6">{children}</main>
    </div>
  );
}
