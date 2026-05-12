import { useId } from 'react';

import { CrudModal } from './CrudModal';

type DeleteConfirmProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  isPending?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function DeleteConfirm({
  open,
  title,
  message,
  confirmLabel = 'Confirm delete',
  isPending = false,
  onCancel,
  onConfirm,
}: DeleteConfirmProps) {
  const messageId = useId();

  if (!open) {
    return null;
  }

  return (
    <CrudModal
      open={open}
      title={title}
      onClose={onCancel}
      descriptionId={messageId}
      maxWidthClassName="max-w-md border-rose-500/30"
    >
      <div className="space-y-6">
        <p id={messageId} className="text-sm leading-6 text-stone-700">
          {message}
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isPending}
            onClick={onConfirm}
            className="rounded-full border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </CrudModal>
  );
}
