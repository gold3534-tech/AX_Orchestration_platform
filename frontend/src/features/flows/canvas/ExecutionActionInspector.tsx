import type { FlowCanvasDraft, FlowCanvasNodeDraft } from '../hooks';

type ExecutionActionApprovalMode = 'never' | 'every_run';

type ExecutionActionInspectorProps = {
  draft: FlowCanvasDraft;
  actionNode: FlowCanvasNodeDraft;
  onChangeDraft: (draft: FlowCanvasDraft) => void;
  onClose: () => void;
};

function normalizedApprovalMode(value: unknown): ExecutionActionApprovalMode {
  return value === 'every_run' ? 'every_run' : 'never';
}

export function ExecutionActionInspector({
  draft,
  actionNode,
  onChangeDraft,
  onClose,
}: ExecutionActionInspectorProps) {
  const approvalMode = normalizedApprovalMode(actionNode.data.approvalMode);
  const titleId = `execution-action-config-title-${actionNode.id.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

  function updateApprovalMode(nextMode: ExecutionActionApprovalMode) {
    onChangeDraft({
      ...draft,
      nodes: draft.nodes.map((node) =>
        node.id === actionNode.id ? { ...node, data: { ...node.data, approvalMode: nextMode } } : node,
      ),
    });
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-stone-950/30 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-xl rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[6px_6px_0_#7a5739]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-700">Execution action</p>
            <h3 id={titleId} className="mt-1 text-base font-semibold text-stone-950">
              {String(actionNode.data.actionKey ?? 'Select action')}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-1 text-xs font-bold text-[#22170f] hover:bg-[#ffe6b3]"
          >
            Close
          </button>
        </div>

        <label className="mt-4 grid gap-1">
          <span className="text-xs font-semibold text-stone-700">Approval</span>
          <select
            value={approvalMode}
            onChange={(event) => updateApprovalMode(normalizedApprovalMode(event.target.value))}
            className="rounded-xl border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-900"
          >
            <option value="never">Never</option>
            <option value="every_run">Every run</option>
          </select>
        </label>
      </section>
    </div>
  );
}
