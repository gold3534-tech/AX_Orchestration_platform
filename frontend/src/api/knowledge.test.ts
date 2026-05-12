import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getStoredAccessToken } from '../hooks/useAuth';
import { uploadKnowledge } from './knowledge';

vi.mock('../hooks/useAuth', () => ({
  getStoredAccessToken: vi.fn(),
}));

const mockGetStoredAccessToken = vi.mocked(getStoredAccessToken);

const knowledgeItem = {
  id: 'k1',
  name: 'Product FAQ',
  description: 'Support answers',
  status: 'ready',
  source_file_name: 'faq.txt',
  source_file_size: 128,
  source_mime_type: 'text/plain',
  embedding_provider: 'openai',
  embedding_model: 'text-embedding-3-small',
  chunk_count: 2,
  attached_agent_count: 0,
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:00:00Z',
};

describe('uploadKnowledge', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    mockGetStoredAccessToken.mockReturnValue(null);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('posts multipart file metadata with authorization and no manual content type', async () => {
    const fetchMock = vi.mocked(fetch);
    const file = new File(['hello'], 'faq.txt', { type: 'text/plain' });
    mockGetStoredAccessToken.mockReturnValue('token-123');
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue(knowledgeItem),
    } as unknown as Response);

    const result = await uploadKnowledge({
      file,
      name: 'Product FAQ',
      description: 'Support answers',
    });

    expect(result).toEqual({ data: knowledgeItem });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/knowledge/upload',
      expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      }),
    );

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = init.body as FormData;
    const headers = init.headers as Headers;

    expect(body.get('file')).toBe(file);
    expect(body.get('name')).toBe('Product FAQ');
    expect(body.get('description')).toBe('Support answers');
    expect(headers.get('Authorization')).toBe('Bearer token-123');
    expect(headers.has('Content-Type')).toBe(false);
  });

  it('omits authorization when no stored token exists', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue(knowledgeItem),
    } as unknown as Response);

    await uploadKnowledge({ file: new File(['hello'], 'faq.txt', { type: 'text/plain' }) });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Headers;

    expect(headers.has('Authorization')).toBe(false);
  });

  it('returns parsed error JSON for non-ok responses', async () => {
    const fetchMock = vi.mocked(fetch);
    const parsedJson = { detail: 'Unsupported file type.' };
    fetchMock.mockResolvedValueOnce({
      ok: false,
      json: vi.fn().mockResolvedValue(parsedJson),
    } as unknown as Response);

    await expect(uploadKnowledge({ file: new File(['hello'], 'faq.exe') })).resolves.toEqual({
      error: parsedJson,
    });
  });

  it('returns fallback detail when non-ok response JSON cannot be parsed', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({
      ok: false,
      json: vi.fn().mockRejectedValue(new Error('Invalid JSON')),
    } as unknown as Response);

    await expect(uploadKnowledge({ file: new File(['hello'], 'faq.txt') })).resolves.toEqual({
      error: { detail: 'Knowledge upload failed.' },
    });
  });
});
