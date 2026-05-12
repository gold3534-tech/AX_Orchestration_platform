import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { vi } from 'vitest';
import { OutputPreview, RawJsonInspect, extractOutputPreview } from '../../src/features/runs/OutputPreview';
import { setStoredAccessToken } from '../../src/hooks/useAuth';

const tinyPngBase64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=';

test('extracts image urls and captions from nested output values', () => {
  const preview = extractOutputPreview({
    data: {
      images: [
        {
          image_url: 'https://example.com/card.png',
          image_description: 'Generated card image',
        },
      ],
    },
  });

  expect(preview.images).toEqual([
    {
      src: 'https://example.com/card.png',
      caption: 'Generated card image',
    },
  ]);
});

test('extracts Dalle-3 base64 image output with revised prompt captions', () => {
  const preview = extractOutputPreview({
    data: [
      {
        b64_json: tinyPngBase64,
        revised_prompt: 'A tiny image',
      },
    ],
  });

  expect(preview.images).toEqual([
    {
      src: `data:image/png;base64,${tinyPngBase64}`,
      caption: 'A tiny image',
    },
  ]);
});

test('renders base64 image output as an image card', () => {
  render(<OutputPreview value={{ b64_json: tinyPngBase64, revised_prompt: 'A tiny image' }} />);

  const image = screen.getByRole('img', { name: /a tiny image/i });
  expect(image).toHaveAttribute('src', `data:image/png;base64,${tinyPngBase64}`);
  expect(screen.getByText(/a tiny image/i)).toBeInTheDocument();
});

test('renders AX artifact preview urls as authenticated image cards', async () => {
  setStoredAccessToken('preview-token');
  const createObjectUrl = vi.fn().mockReturnValue('blob:artifact-preview');
  const revokeObjectUrl = vi.fn();
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: createObjectUrl,
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: revokeObjectUrl,
  });
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    blob: () => Promise.resolve(new Blob(['image-bytes'], { type: 'image/png' })),
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <OutputPreview
      value={{
        artifact_id: 'artifact-1',
        artifact_type: 'image',
        preview_url: '/api/run-artifacts/artifact-1/content',
        prompt: 'Generated dessert image',
      }}
    />,
  );

  const image = await screen.findByRole('img', { name: /generated dessert image/i });
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/run-artifacts/artifact-1/content',
    expect.objectContaining({
      headers: expect.any(Headers),
    }),
  );
  const headers = fetchMock.mock.calls[0][1].headers as Headers;
  expect(headers.get('Authorization')).toBe('Bearer preview-token');
  expect(image).toHaveAttribute('src', 'blob:artifact-preview');

  vi.unstubAllGlobals();
  setStoredAccessToken(null);
});

test('deduplicates repeated artifact preview and download urls', () => {
  const preview = extractOutputPreview({
    artifacts: [
      {
        artifact_id: 'artifact-1',
        artifact_type: 'image',
        preview_url: '/api/run-artifacts/artifact-1/content',
        download_url: '/api/run-artifacts/artifact-1/content',
        metadata_json: {
          preview_url: '/api/run-artifacts/artifact-1/content',
          download_url: '/api/run-artifacts/artifact-1/content',
        },
      },
      {
        artifact_id: 'artifact-2',
        artifact_type: 'image',
        preview_url: '/api/run-artifacts/artifact-2/content',
        download_url: '/api/run-artifacts/artifact-2/content',
      },
    ],
  });

  expect(preview.images).toEqual([
    {
      src: '/api/run-artifacts/artifact-1/content',
      caption: undefined,
    },
    {
      src: '/api/run-artifacts/artifact-2/content',
      caption: undefined,
    },
  ]);
});

test('raw json inspect truncates base64 image values', () => {
  render(<RawJsonInspect value={{ b64_json: `${tinyPngBase64}${tinyPngBase64}${tinyPngBase64}` }} />);

  expect(screen.getByText(/base64 image truncated/i)).toBeInTheDocument();
  expect(screen.queryByText(new RegExp(tinyPngBase64.repeat(3)))).not.toBeInTheDocument();
});

test('raw json inspect truncates data image values', () => {
  render(<RawJsonInspect value={{ image: `data:image/png;base64,${tinyPngBase64}${tinyPngBase64}` }} />);

  expect(screen.getByText(/base64 image truncated/i)).toBeInTheDocument();
  expect(screen.queryByText(new RegExp(tinyPngBase64.repeat(2)))).not.toBeInTheDocument();
});
