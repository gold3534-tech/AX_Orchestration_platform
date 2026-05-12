import { type ReactNode } from 'react';

type PageHeaderProps = {
  title: string;
  description?: ReactNode;
};

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <header className="mb-5">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#6f4bd9]">Workspace</p>
      <h1 className="mt-2 text-2xl font-black text-stone-950 2xl:text-3xl">{title}</h1>
      {description ? <p className="mt-2 max-w-2xl text-sm font-medium text-stone-700">{description}</p> : null}
    </header>
  );
}
