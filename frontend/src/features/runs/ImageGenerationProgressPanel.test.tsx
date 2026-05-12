import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { ImageGenerationProgressPanel } from './ImageGenerationProgressPanel';
import type { ImageProgressGroup } from './imageProgressModel';

function group(overrides: Partial<ImageProgressGroup> = {}): ImageProgressGroup {
  return {
    groupId: 'crew:image',
    nodeId: 'crew:image',
    taskId: null,
    completedCount: 0,
    totalCount: 3,
    slots: [],
    ...overrides,
  };
}

test('renders nothing when there are no image progress groups', () => {
  const { container } = render(<ImageGenerationProgressPanel groups={[]} />);

  expect(container).toBeEmptyDOMElement();
});

test('renders a generating image slot with elapsed time and prompt preview', () => {
  render(
    <ImageGenerationProgressPanel
      groups={[
        group({
          slots: [
            {
              index: 0,
              status: 'generating',
              promptPreview: 'A glossy launch card',
              elapsedMs: 45000,
            },
          ],
        }),
      ]}
    />,
  );

  expect(screen.getByRole('heading', { name: /image generation progress/i })).toBeInTheDocument();
  expect(screen.getByText(/crew:image/i)).toBeInTheDocument();
  expect(screen.getByText(/0 \/ 3 images complete/i)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: /slide 1/i })).toBeInTheDocument();
  expect(screen.getByText(/generating/i)).toBeInTheDocument();
  expect(screen.getByText(/45s/i)).toBeInTheDocument();
  expect(screen.getByText(/a glossy launch card/i)).toBeInTheDocument();
});

test('renders completed artifact metadata and link', () => {
  render(
    <ImageGenerationProgressPanel
      groups={[
        group({
          completedCount: 1,
          slots: [
            {
              index: 0,
              status: 'completed',
              promptPreview: 'A finished visual',
              artifactId: 'artifact-1',
              previewUrl: '/api/run-artifacts/artifact-1/content',
              mimeType: 'image/png',
              elapsedMs: 5000,
            },
          ],
        }),
      ]}
    />,
  );

  expect(screen.getByText(/1 \/ 3 images complete/i)).toBeInTheDocument();
  expect(screen.getByText(/completed/i)).toBeInTheDocument();
  expect(screen.getByText(/artifact-1/i)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /open artifact artifact-1/i })).toHaveAttribute(
    'href',
    '/api/run-artifacts/artifact-1/content',
  );
  expect(screen.getByText(/image\/png/i)).toBeInTheDocument();
});

test('shows a long-running hint for generating slots older than two minutes', () => {
  render(
    <ImageGenerationProgressPanel
      groups={[
        group({
          slots: [
            {
              index: 0,
              status: 'generating',
              elapsedMs: 121000,
            },
          ],
        }),
      ]}
    />,
  );

  expect(screen.getByText(/taking longer than usual/i)).toBeInTheDocument();
});

test('renders failed image errors and retryable marker', () => {
  render(
    <ImageGenerationProgressPanel
      groups={[
        group({
          slots: [
            {
              index: 0,
              status: 'failed',
              errorMessage: 'Provider timeout',
              rawError: '{"code":"timeout"}',
              retryable: true,
              elapsedMs: 30000,
            },
          ],
        }),
      ]}
    />,
  );

  expect(screen.getByText(/failed/i)).toBeInTheDocument();
  expect(screen.getByText(/provider timeout/i)).toBeInTheDocument();
  expect(screen.getByText(/"code":"timeout"/i)).toBeInTheDocument();
  expect(screen.getByText(/retryable/i)).toBeInTheDocument();
});
