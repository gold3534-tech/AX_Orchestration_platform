import { Trash2, Upload, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { PageFrame } from '../../components/layout/PageFrame';
import { EmptyState } from '../../components/platform/EmptyState';
import { PageHeader } from '../../components/platform/PageHeader';
import { useDeleteKnowledge, useKnowledgeItems, useUploadKnowledge } from './hooks';

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function uploadErrorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return 'Knowledge could not be uploaded.';
}

export function KnowledgePage() {
  const knowledgeQuery = useKnowledgeItems();
  const uploadKnowledge = useUploadKnowledge();
  const deleteKnowledge = useDeleteKnowledge();
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const uploadButtonRef = useRef<HTMLButtonElement | null>(null);
  const uploadDialogRef = useRef<HTMLDivElement | null>(null);
  const uploadPanelRef = useRef<HTMLFormElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const items = knowledgeQuery.data ?? [];
  const canUpload = Boolean(selectedFile && uploadName.trim() && !uploadKnowledge.isPending);

  useEffect(() => {
    if (!isUploadOpen) return;

    if (uploadKnowledge.isPending) {
      uploadDialogRef.current?.focus();
    } else {
      fileInputRef.current?.focus();
    }
  }, [isUploadOpen, uploadKnowledge.isPending]);

  function resetUploadForm() {
    setSelectedFile(null);
    setUploadName('');
    setUploadDescription('');
    setUploadError(null);
  }

  function closeUploadDialog(force = false) {
    if (uploadKnowledge.isPending && !force) return;

    resetUploadForm();
    setIsUploadOpen(false);
    uploadButtonRef.current?.focus();
  }

  function handleUploadDialogKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      if (!uploadKnowledge.isPending) {
        event.preventDefault();
        closeUploadDialog();
      }
      return;
    }

    if (event.key !== 'Tab') return;

    const focusableElements = Array.from(
      uploadPanelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? [],
    );
    if (focusableElements.length === 0) {
      event.preventDefault();
      uploadDialogRef.current?.focus();
      return;
    }

    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (event.shiftKey && document.activeElement === firstElement) {
      event.preventDefault();
      lastElement.focus();
    } else if (!event.shiftKey && document.activeElement === lastElement) {
      event.preventDefault();
      firstElement.focus();
    }
  }

  function handleFileSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setUploadError(null);

    if (file && !uploadName.trim()) {
      setUploadName(file.name.replace(/\.pdf$/i, ''));
    }
  }

  async function handleUploadSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile || !uploadName.trim() || uploadKnowledge.isPending) return;

    setUploadError(null);
    try {
      await uploadKnowledge.mutateAsync({
        file: selectedFile,
        name: uploadName.trim(),
        description: uploadDescription,
      });
      closeUploadDialog(true);
    } catch (error) {
      setUploadError(uploadErrorMessage(error));
    }
  }

  async function handleDeleteKnowledge(knowledgeItemId: string) {
    setDeleteError(null);
    try {
      await deleteKnowledge.mutateAsync(knowledgeItemId);
    } catch {
      setDeleteError('Knowledge could not be deleted.');
    }
  }

  return (
    <PageFrame>
      <PageHeader
        title="Knowledge"
        description="Uploaded files that can be attached to Agents as private retrieval context."
      />
      <section className="pixel-panel bg-[#fff6df] p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-xl font-black text-[#22170f]">Knowledge Library</h2>
          <button
            type="button"
            ref={uploadButtonRef}
            aria-label="Upload knowledge file"
            onClick={() => setIsUploadOpen(true)}
            className="pixel-button inline-flex items-center gap-2 bg-[#2f9b96] px-3 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa]"
          >
            <Upload size={16} /> Upload
          </button>
        </div>
        {isUploadOpen ? (
          <div
            ref={uploadDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="knowledge-upload-title"
            tabIndex={-1}
            onKeyDown={handleUploadDialogKeyDown}
            className="fixed inset-0 z-50 flex items-center justify-center bg-[#22170f]/50 px-4 py-6"
          >
            <form
              ref={uploadPanelRef}
              onSubmit={(event) => {
                void handleUploadSubmit(event);
              }}
              className="w-full max-w-lg rounded-md border-2 border-[#7a5739] bg-[#fff6df] p-5 shadow-[8px_8px_0_#7a5739]"
            >
              <div className="mb-4 flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h3 id="knowledge-upload-title" className="text-lg font-black text-[#22170f]">
                    Upload PDF
                  </h3>
                  <p className="mt-1 text-sm text-stone-600">Add a PDF for private Agent retrieval.</p>
                </div>
                <button
                  type="button"
                  aria-label="Close upload dialog"
                  onClick={() => closeUploadDialog()}
                  disabled={uploadKnowledge.isPending}
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border-2 border-[#7a5739] bg-[#fffaf0] text-stone-700 hover:bg-[#ffe6b3]"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-4">
                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-stone-800">PDF file</span>
                  <input
                    type="file"
                    ref={fileInputRef}
                    aria-label="PDF file"
                    accept="application/pdf,.pdf"
                    disabled={uploadKnowledge.isPending}
                    onChange={handleFileSelected}
                    className="block w-full text-sm text-stone-700 file:mr-3 file:rounded-md file:border-2 file:border-[#7a5739] file:bg-[#fffaf0] file:px-3 file:py-2 file:text-sm file:font-bold file:text-[#22170f]"
                  />
                </label>

                {selectedFile ? (
                  <p className="min-w-0 break-all rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-700">
                    {selectedFile.name} · {formatBytes(selectedFile.size)}
                  </p>
                ) : null}

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-stone-800">Name</span>
                  <input
                    type="text"
                    value={uploadName}
                    disabled={uploadKnowledge.isPending}
                    onChange={(event) => setUploadName(event.target.value)}
                    className="w-full rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-950 outline-none focus:border-[#2f9b96]"
                  />
                </label>

                <label className="block">
                  <span className="mb-1 block text-sm font-medium text-stone-800">Description</span>
                  <textarea
                    value={uploadDescription}
                    disabled={uploadKnowledge.isPending}
                    onChange={(event) => setUploadDescription(event.target.value)}
                    rows={3}
                    className="w-full resize-y rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm text-stone-950 outline-none focus:border-[#2f9b96]"
                  />
                </label>

                {uploadError ? (
                  <p role="alert" className="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                    {uploadError}
                  </p>
                ) : null}
              </div>

              <div className="mt-5 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => closeUploadDialog()}
                  disabled={uploadKnowledge.isPending}
                  className="pixel-button border-[#7a5739] bg-[#fffaf0] px-3 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!canUpload}
                  className="pixel-button bg-[#2f9b96] px-3 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa] disabled:cursor-not-allowed disabled:border-stone-200 disabled:bg-stone-100 disabled:text-stone-500"
                >
                  {uploadKnowledge.isPending ? 'Uploading' : 'Upload PDF'}
                </button>
              </div>
            </form>
          </div>
        ) : null}
        {deleteError ? (
          <p role="alert" className="mb-4 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {deleteError}
          </p>
        ) : null}
        {knowledgeQuery.isLoading ? <p className="text-sm text-stone-500">Loading knowledge...</p> : null}
        {knowledgeQuery.isError ? <p className="text-sm text-rose-700">Unable to load knowledge.</p> : null}
        {!knowledgeQuery.isLoading && !knowledgeQuery.isError && items.length === 0 ? (
          <EmptyState title="No knowledge yet" description="Upload a file to make it available for Agent retrieval." />
        ) : null}
        {items.length > 0 ? (
          <div className="overflow-x-auto rounded-md border-2 border-[#7a5739] bg-[#fffaf0]">
            <table className="min-w-full table-fixed text-sm">
              <thead className="bg-[#f8e8c8] text-left text-xs font-bold uppercase text-[#7a5739]">
                <tr>
                  <th className="w-[24%] px-4 py-3">Name</th>
                  <th className="w-[12%] px-4 py-3">Status</th>
                  <th className="w-[30%] px-4 py-3">File</th>
                  <th className="w-[10%] px-4 py-3">Chunks</th>
                  <th className="w-[12%] px-4 py-3">Attached</th>
                  <th className="w-[12%] px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id} className="border-t border-[#7a5739]/30">
                    <td className="px-4 py-3 font-medium text-stone-950">
                      <div className="min-w-0 max-w-72 truncate" title={item.name}>
                        {item.name}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-stone-700">
                      <span className="break-all">{item.status}</span>
                    </td>
                    <td className="px-4 py-3 text-stone-700">
                      <div className="min-w-0 max-w-96 break-all" title={item.source_file_name}>
                        {item.source_file_name} · {formatBytes(item.source_file_size)}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-stone-700">{item.chunk_count}</td>
                    <td className="px-4 py-3 text-stone-700">
                      {item.attached_agent_count} {item.attached_agent_count === 1 ? 'Agent' : 'Agents'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        aria-label={`Delete ${item.name}`}
                        disabled={deleteKnowledge.isPending}
                        onClick={() => {
                          void handleDeleteKnowledge(item.id);
                        }}
                        className="inline-flex items-center gap-2 text-rose-700 disabled:cursor-not-allowed disabled:text-stone-400"
                      >
                        <Trash2 size={16} /> Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </PageFrame>
  );
}
