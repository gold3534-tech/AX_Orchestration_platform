import { type ReactNode } from 'react';

type EmptyStateProps = {
  title: string;
  description?: ReactNode;
};

export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="rounded-md border-2 border-dashed border-[#9a7a54] bg-[#fff6df] p-6 shadow-[3px_3px_0_rgba(80,48,24,0.12)]">
      <h2 className="text-lg font-black text-stone-950">{title}</h2>
      {description ? <p className="mt-2 text-sm font-semibold text-stone-700">{description}</p> : null}
    </div>
  );
}
