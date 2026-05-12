import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ActionButtonVariant = 'primary' | 'secondary' | 'soft';

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  isPending?: boolean;
  pendingLabel?: string;
  variant?: ActionButtonVariant;
  children: ReactNode;
};

const variantClassName: Record<ActionButtonVariant, string> = {
  primary: 'bg-[#2f9b96] text-white hover:bg-[#3fb0aa] disabled:bg-stone-200 disabled:text-stone-500',
  secondary: 'border-[#7a5739] bg-[#fffaf0] text-[#22170f] hover:bg-[#ffe6b3] disabled:text-stone-400',
  soft: 'border-[#ef8b2c] bg-[#ffe6b3] text-[#5b3424] hover:bg-[#ffd98a] disabled:text-stone-400',
};

export function ActionButton({
  isPending = false,
  pendingLabel,
  variant = 'secondary',
  disabled,
  children,
  className = '',
  ...props
}: ActionButtonProps) {
  const label = isPending ? pendingLabel ?? 'Working...' : children;

  return (
    <button
      type="button"
      disabled={disabled || isPending}
      className={`pixel-button inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-70 ${variantClassName[variant]} ${className}`}
      {...props}
    >
      {isPending ? (
        <span
          data-testid="action-button-spinner"
          aria-hidden="true"
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : null}
      <span>{label}</span>
    </button>
  );
}
