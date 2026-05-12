import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { KnowledgePage } from './KnowledgePage';

const uploadMutateAsync = vi.fn();
const deleteMutateAsync = vi.fn();
let uploadIsPending = false;
let deleteIsPending = false;
let knowledgeState: {
  data: Array<{
    id: string;
    name: string;
    status: string;
    source_file_name: string;
    source_file_size: number;
    source_mime_type: string;
    chunk_count: number;
    attached_agent_count: number;
    created_at: string;
  }>;
  isLoading: boolean;
  isError: boolean;
} = {
  data: [],
  isLoading: false,
  isError: false,
};

vi.mock('./hooks', () => ({
  useKnowledgeItems: () => knowledgeState,
  useUploadKnowledge: () => ({ mutateAsync: uploadMutateAsync, isPending: uploadIsPending }),
  useDeleteKnowledge: () => ({ mutateAsync: deleteMutateAsync, isPending: deleteIsPending }),
}));

function setKnowledgeState(overrides: Partial<typeof knowledgeState> = {}) {
  knowledgeState = {
    data: [
      {
        id: 'k1',
        name: 'Product FAQ',
        status: 'ready',
        source_file_name: 'faq.txt',
        source_file_size: 128,
        source_mime_type: 'text/plain',
        chunk_count: 2,
        attached_agent_count: 1,
        created_at: '2026-05-05T00:00:00Z',
      },
    ],
    isLoading: false,
    isError: false,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <KnowledgePage />
    </QueryClientProvider>,
  );
}

describe('KnowledgePage', () => {
  beforeEach(() => {
    uploadMutateAsync.mockReset();
    deleteMutateAsync.mockReset();
    uploadIsPending = false;
    deleteIsPending = false;
    setKnowledgeState();
  });

  it('renders uploaded knowledge rows', () => {
    renderPage();

    expect(screen.getByText('Knowledge')).toBeInTheDocument();
    expect(screen.getByText('Product FAQ')).toBeInTheDocument();
    expect(screen.getByText('1 Agent')).toBeInTheDocument();
  });

  it('keeps delete accessible and disables it while pending', () => {
    deleteIsPending = true;

    renderPage();

    const deleteButton = screen.getByRole('button', { name: 'Delete Product FAQ' });
    expect(deleteButton).toBeDisabled();
  });

  it('shows a visible error when delete fails', async () => {
    deleteMutateAsync.mockRejectedValueOnce(new Error('Delete failed'));

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Delete Product FAQ' }));

    await waitFor(() => {
      expect(screen.getByText('Knowledge could not be deleted.')).toBeInTheDocument();
    });
  });

  it('uploads a selected PDF file', async () => {
    uploadMutateAsync.mockResolvedValueOnce({});
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Upload knowledge file' }));

    const file = new File(['%PDF demo'], 'Product FAQ.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('PDF file'), { target: { files: [file] } });

    expect(screen.getByDisplayValue('Product FAQ')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF' }));

    await waitFor(() => {
      expect(uploadMutateAsync).toHaveBeenCalledWith({ file, name: 'Product FAQ', description: '' });
    });
  });

  it('shows upload errors', async () => {
    uploadMutateAsync.mockRejectedValueOnce({ detail: 'Knowledge storage is not configured.' });
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Upload knowledge file' }));
    const file = new File(['%PDF demo'], 'Product FAQ.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('PDF file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload PDF' }));

    await waitFor(() => {
      expect(screen.getByText('Knowledge storage is not configured.')).toBeInTheDocument();
    });
  });

  it('restores focus after closing the upload dialog with the close button or Escape', async () => {
    renderPage();

    const uploadButton = screen.getByRole('button', { name: 'Upload knowledge file' });
    fireEvent.click(uploadButton);

    await waitFor(() => {
      expect(screen.getByLabelText('PDF file')).toHaveFocus();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Close upload dialog' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(uploadButton).toHaveFocus();

    fireEvent.click(uploadButton);

    await waitFor(() => {
      expect(screen.getByLabelText('PDF file')).toHaveFocus();
    });

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(uploadButton).toHaveFocus();
  });

  it('prevents closing and duplicate submits while upload is pending', () => {
    const { rerender } = renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Upload knowledge file' }));
    const file = new File(['%PDF demo'], 'Product FAQ.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('PDF file'), { target: { files: [file] } });

    uploadIsPending = true;
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <KnowledgePage />
      </QueryClientProvider>,
    );

    expect(screen.getByLabelText('PDF file')).toBeDisabled();
    expect(screen.getByDisplayValue('Product FAQ')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Close upload dialog' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Uploading' })).toBeDisabled();

    const dialog = screen.getByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Tab' });

    expect(dialog).toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: 'Uploading' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.keyDown(dialog, { key: 'Escape' });

    expect(uploadMutateAsync).not.toHaveBeenCalled();
    expect(dialog).toBeInTheDocument();
  });

  it('renders file sizes and loading state', () => {
    const { rerender } = renderPage();

    expect(screen.getByText(/faq\.txt/)).toHaveTextContent('128 B');

    setKnowledgeState({ data: [], isLoading: true });
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <KnowledgePage />
      </QueryClientProvider>,
    );

    expect(screen.getByText('Loading knowledge...')).toBeInTheDocument();
  });
});
