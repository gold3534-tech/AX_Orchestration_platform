import { createElement, useEffect, useState } from 'react';
import { apiBaseUrl } from '../../api/client';
import { getStoredAccessToken } from '../../hooks/useAuth';

export type PreviewImage = {
  src: string;
  caption?: string;
};

export type OutputPreviewModel = {
  images: PreviewImage[];
  textBlocks: string[];
  records: Record<string, unknown>[];
};

const imageUrlKeys = new Set(['image_url', 'imageUrl', 'preview_url', 'previewUrl', 'download_url', 'downloadUrl', 'url']);
const base64Keys = new Set(['b64_json', 'base64', 'image_base64']);
const captionKeys = ['revised_prompt', 'image_description', 'description', 'prompt', 'caption'];
const hiddenPreviewKeys = new Set(['raw', 'raw_output', 'rawOutput', 'raw_data', 'rawData']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function looksLikeImageUrl(value: string) {
  return (
    /^https?:\/\/.+\.(png|jpe?g|webp|gif)(\?.*)?$/i.test(value) ||
    /^\/api\/run-artifacts\/[0-9A-Za-z-]+\/content$/i.test(value) ||
    value.startsWith('data:image/')
  );
}

function isInternalArtifactUrl(value: string) {
  return /^\/api\/run-artifacts\/[0-9A-Za-z-]+\/content$/i.test(value);
}

function fetchUrlForImage(src: string) {
  if (!isInternalArtifactUrl(src) || !apiBaseUrl) {
    return src;
  }
  return new URL(src, apiBaseUrl).toString();
}

function AuthenticatedImage({ src, alt, className }: { src: string; alt: string; className: string }) {
  const [resolvedSrc, setResolvedSrc] = useState(isInternalArtifactUrl(src) ? '' : src);

  useEffect(() => {
    if (!isInternalArtifactUrl(src)) {
      setResolvedSrc(src);
      return undefined;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    const headers = new Headers();
    const accessToken = getStoredAccessToken();
    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`);
    }

    fetch(fetchUrlForImage(src), { headers })
      .then((response) => {
        if (!response.ok) {
          throw new Error('Artifact image preview could not be loaded.');
        }
        return response.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setResolvedSrc(objectUrl);
      })
      .catch(() => {
        if (!cancelled) {
          setResolvedSrc('');
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [src]);

  if (!resolvedSrc) {
    return createElement('div', { className, role: 'status', 'aria-label': `${alt} loading` });
  }

  return createElement('img', {
    src: resolvedSrc,
    alt,
    className,
  });
}

function looksLikeBase64Image(value: string) {
  return /^[A-Za-z0-9+/]+={0,2}$/.test(value) && value.length > 40;
}

function captionFor(record: Record<string, unknown>) {
  for (const key of captionKeys) {
    const value = record[key];
    if (typeof value === 'string' && value.trim()) {
      return value;
    }
  }
  return undefined;
}

function visit(value: unknown, images: PreviewImage[], textBlocks: string[], records: Record<string, unknown>[]) {
  if (typeof value === 'string') {
    if (value.trim() && !looksLikeBase64Image(value) && !value.startsWith('data:image/')) {
      textBlocks.push(value);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => visit(item, images, textBlocks, records));
    return;
  }
  if (!isRecord(value)) {
    return;
  }

  records.push(value);
  const caption = captionFor(value);
  for (const [key, nestedValue] of Object.entries(value)) {
    if (hiddenPreviewKeys.has(key)) {
      continue;
    }
    if (typeof nestedValue === 'string' && captionKeys.includes(key) && nestedValue === caption) {
      continue;
    }
    if (typeof nestedValue === 'string' && imageUrlKeys.has(key) && looksLikeImageUrl(nestedValue)) {
      images.push({ src: nestedValue, caption });
      continue;
    }
    if (typeof nestedValue === 'string' && nestedValue.startsWith('data:image/')) {
      images.push({ src: nestedValue, caption });
      continue;
    }
    if (typeof nestedValue === 'string' && base64Keys.has(key) && looksLikeBase64Image(nestedValue)) {
      images.push({ src: `data:image/png;base64,${nestedValue}`, caption });
      continue;
    }
    visit(nestedValue, images, textBlocks, records);
  }
}

function dedupeImages(images: PreviewImage[]) {
  const seen = new Set<string>();
  const uniqueImages: PreviewImage[] = [];
  for (const image of images) {
    if (seen.has(image.src)) {
      continue;
    }
    seen.add(image.src);
    uniqueImages.push(image);
  }
  return uniqueImages;
}

export function extractOutputPreview(value: unknown): OutputPreviewModel {
  const images: PreviewImage[] = [];
  const textBlocks: string[] = [];
  const records: Record<string, unknown>[] = [];
  visit(value, images, textBlocks, records);
  return { images: dedupeImages(images), textBlocks: [...new Set(textBlocks)].slice(0, 6), records: records.slice(0, 8) };
}

export function stringifyForInspect(value: unknown) {
  return JSON.stringify(
    value ?? {},
    (key, nestedValue) => {
      if (typeof nestedValue !== 'string') return nestedValue;
      if (nestedValue.startsWith('data:image/') || base64Keys.has(key)) {
        return `base64 image truncated (${nestedValue.length} chars)`;
      }
      if (looksLikeBase64Image(nestedValue) && nestedValue.length > 240) {
        return `base64 image truncated (${nestedValue.length} chars)`;
      }
      return nestedValue;
    },
    2,
  );
}

function keyValueSummaryElement(records: OutputPreviewModel['records']) {
  const firstRecord = records[0] ?? {};
  const entries = Object.entries(firstRecord)
    .filter(
      ([key, value]) =>
        !base64Keys.has(key) &&
        !captionKeys.includes(key) &&
        !hiddenPreviewKeys.has(key) &&
        (value === null || typeof value !== 'object'),
    )
    .slice(0, 8);
  if (entries.length === 0) return null;
  return createElement(
    'dl',
    { className: 'grid gap-3 sm:grid-cols-2' },
    entries.map(([key, value]) =>
      createElement(
        'div',
        { key, className: 'rounded-md border-2 border-[#7a5739]/40 bg-[#fffaf0] p-3' },
        createElement('dt', { className: 'text-xs font-semibold uppercase text-stone-500' }, key),
        createElement('dd', { className: 'mt-1 break-words text-sm text-stone-900' }, String(value)),
      ),
    ),
  );
}

export function OutputPreview({ value }: { value: unknown }) {
  const preview = extractOutputPreview(value);
  const hasContent = preview.images.length > 0 || preview.textBlocks.length > 0 || preview.records.length > 0;
  if (!hasContent) {
    return createElement('p', { className: 'text-sm text-stone-500' }, 'No output preview available.');
  }

  return createElement(
    'div',
    { className: 'space-y-4' },
    preview.images.length > 0
      ? createElement(
          'div',
          { className: 'grid gap-4 md:grid-cols-2' },
          preview.images.map((image, index) =>
            createElement(
              'figure',
              {
                key: `${image.src}-${index}`,
                className: 'overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fffaf0]',
              },
              createElement(AuthenticatedImage, {
                src: image.src,
                alt: image.caption ?? `Generated image ${index + 1}`,
                className: 'aspect-square w-full object-cover',
              }),
              image.caption
                ? createElement(
                    'figcaption',
                    { className: 'border-t-2 border-[#7a5739] p-3 text-sm text-stone-700' },
                    image.caption,
                  )
                : null,
            ),
          ),
        )
      : null,
    ...preview.textBlocks.map((text, index) =>
      createElement(
        'p',
        {
          key: `${text}-${index}`,
          className:
            'whitespace-pre-wrap rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4 text-sm leading-6 text-stone-800',
        },
        text,
      ),
    ),
    keyValueSummaryElement(preview.records),
  );
}

export function RawJsonInspect({ value }: { value: unknown }) {
  return createElement(
    'pre',
    { className: 'max-h-[32rem] overflow-auto rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-3 text-xs text-stone-700' },
    stringifyForInspect(value),
  );
}
