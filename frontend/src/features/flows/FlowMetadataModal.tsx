import { useEffect, useState, type FormEvent } from 'react';
import { CrudModal } from '../../components/shared/CrudModal';

export type FlowMetadataValues = {
  name: string;
  description: string;
};

type FlowMetadataModalProps = {
  open: boolean;
  title: string;
  submitLabel: string;
  initialValues: FlowMetadataValues;
  isSubmitting?: boolean;
  onClose: () => void;
  onSubmit: (values: FlowMetadataValues) => void | Promise<void>;
};

export function FlowMetadataModal({
  open,
  title,
  submitLabel,
  initialValues,
  isSubmitting = false,
  onClose,
  onSubmit,
}: FlowMetadataModalProps) {
  const [values, setValues] = useState(initialValues);

  useEffect(() => {
    if (open) {
      setValues(initialValues);
    }
  }, [initialValues, open]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const name = values.name.trim();
    if (!name) {
      return;
    }

    await onSubmit({
      name,
      description: values.description.trim(),
    });
  }

  return (
    <CrudModal open={open} title={title} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4 text-sm text-stone-600">
          Flow는 여러 Crew를 상태, 라우터, HITL 노드와 함께 묶는 실행 단위입니다. 먼저 이름을 만들고 캔버스에서
          조립을 이어가세요.
        </p>
        <label className="block">
          <span className="text-sm font-semibold text-stone-900">Name</span>
          <input
            value={values.name}
            onChange={(event) => setValues((current) => ({ ...current, name: event.target.value }))}
            className="mt-2 w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-4 py-3 text-sm outline-none focus:border-[#2f9b96]"
            placeholder="Content publishing flow"
            autoFocus
          />
        </label>
        <label className="block">
          <span className="text-sm font-semibold text-stone-900">Summary</span>
          <textarea
            value={values.description}
            onChange={(event) => setValues((current) => ({ ...current, description: event.target.value }))}
            className="mt-2 min-h-28 w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-4 py-3 text-sm outline-none focus:border-[#2f9b96]"
            placeholder="Describe what this flow coordinates."
          />
        </label>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="pixel-button border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!values.name.trim() || isSubmitting}
            className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa] disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-500"
          >
            {submitLabel}
          </button>
        </div>
      </form>
    </CrudModal>
  );
}
