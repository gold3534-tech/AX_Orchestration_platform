import { forwardRef, type ComponentPropsWithoutRef, type ReactNode } from 'react';

function cx(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

export type CanvasPanelProps = ComponentPropsWithoutRef<'section'>;

export function CanvasPanel({ children, className, ...props }: CanvasPanelProps) {
  return (
    <section className={cx('pixel-panel bg-[#fff6df] p-3', className)} {...props}>
      {children}
    </section>
  );
}

export type CanvasPanelHeaderProps = {
  eyebrow: ReactNode;
  title: ReactNode;
  description: ReactNode;
  actions?: ReactNode;
  headingLevel?: 2 | 3;
  actionsLabel?: string;
};

export function CanvasPanelHeader({
  eyebrow,
  title,
  description,
  actions,
  headingLevel = 2,
  actionsLabel,
}: CanvasPanelHeaderProps) {
  const Heading = headingLevel === 3 ? 'h3' : 'h2';

  return (
    <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">{eyebrow}</p>
        <Heading className="text-base font-black text-[#22170f]">{title}</Heading>
        <p className="text-xs leading-5 text-stone-600">{description}</p>
      </div>

      {actions ? (
        <div className="flex flex-wrap items-center gap-2" aria-label={actionsLabel}>
          {actions}
        </div>
      ) : null}
    </div>
  );
}

export type CanvasFrameProps = ComponentPropsWithoutRef<'div'>;

export const CanvasFrame = forwardRef<HTMLDivElement, CanvasFrameProps>(function CanvasFrame(
  { children, className, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cx('relative h-[560px] overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#f8e8c8]', className)}
      {...props}
    >
      {children}
    </div>
  );
});

export type CanvasEmptyStateProps = {
  eyebrow: ReactNode;
  title: ReactNode;
  children: ReactNode;
  action?: ReactNode;
  headingLevel?: 3 | 4;
  interactive?: boolean;
  textAlign?: 'left' | 'center';
};

export function CanvasEmptyState({
  eyebrow,
  title,
  children,
  action,
  headingLevel = 3,
  interactive = false,
  textAlign = 'left',
}: CanvasEmptyStateProps) {
  const Heading = headingLevel === 4 ? 'h4' : 'h3';

  return (
    <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center p-6">
      <div
        className={cx(
          interactive && 'pointer-events-auto',
          'max-w-md rounded-md border-2 border-[#7a5739] bg-[#fff6df]/95 p-6 shadow-[6px_6px_0_#7a5739] backdrop-blur',
          textAlign === 'center' && 'text-center',
        )}
      >
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">{eyebrow}</p>
        <Heading className="mt-2 text-lg font-black text-[#22170f]">{title}</Heading>
        <p className="mt-2 text-sm leading-6 text-stone-600">{children}</p>
        {action}
      </div>
    </div>
  );
}
