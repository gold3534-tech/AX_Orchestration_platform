import { describe, expect, it } from 'vitest';
import { buildImageProgressGroups } from './imageProgressModel';

const now = new Date('2026-05-04T12:05:00Z');

function event(overrides: Record<string, unknown>) {
  return {
    id: 'event',
    event_type: 'agent_step',
    node_id: 'crew:image',
    created_at: '2026-05-04T12:00:00Z',
    event_payload_json: {
      image_generation: true,
      prompt_preview: 'A launch card image',
    },
    ...overrides,
  };
}

describe('buildImageProgressGroups', () => {
  it('creates a generating slot from a Nano Banana image start event', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          event_type: 'image_generation_started',
          event_payload_json: {
            tool: 'nano_banana',
            prompt_preview: 'A compact product card',
          },
        }),
      ],
      { now },
    );

    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({
      nodeId: 'crew:image',
      completedCount: 0,
      totalCount: 3,
    });
    expect(groups[0].slots).toEqual([
      expect.objectContaining({
        status: 'generating',
        promptPreview: 'A compact product card',
        elapsedMs: 300000,
      }),
    ]);
  });

  it('turns completion events into completed slots with artifact metadata', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          id: 'start-1',
          event_type: 'image_generation_started',
          created_at: '2026-05-04T12:00:00Z',
        }),
        event({
          id: 'complete-1',
          event_type: 'image_generation_completed',
          created_at: '2026-05-04T12:00:05Z',
          event_payload_json: {
            image_generation: true,
            artifact_id: 'artifact-1',
            preview_url: '/api/run-artifacts/artifact-1/content',
            mime_type: 'image/png',
            prompt_preview: 'Finished prompt',
          },
        }),
      ],
      { now },
    );

    expect(groups[0].completedCount).toBe(1);
    expect(groups[0].slots[0]).toMatchObject({
      status: 'completed',
      promptPreview: 'Finished prompt',
      artifactId: 'artifact-1',
      previewUrl: '/api/run-artifacts/artifact-1/content',
      mimeType: 'image/png',
      elapsedMs: 5000,
    });
  });

  it('keeps three completed slots in event order', () => {
    const groups = buildImageProgressGroups(
      [1, 2, 3].map((index) =>
        event({
          id: `complete-${index}`,
          event_type: 'image_generation_completed',
          created_at: `2026-05-04T12:00:0${index}Z`,
          event_payload_json: {
            image_generation: true,
            artifact_id: `artifact-${index}`,
            prompt_preview: `Prompt ${index}`,
          },
        }),
      ),
      { now },
    );

    expect(groups[0].completedCount).toBe(3);
    expect(groups[0].totalCount).toBe(3);
    expect(groups[0].slots.map((slot) => slot.artifactId)).toEqual(['artifact-1', 'artifact-2', 'artifact-3']);
  });

  it('captures failed image events with friendly and raw errors', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          event_type: 'image_generation_failed',
          event_payload_json: {
            image_generation: true,
            error_message: 'Image moderation failed',
            error: { code: 'content_policy', detail: 'blocked prompt' },
            retryable: true,
          },
        }),
      ],
      { now },
    );

    expect(groups[0].slots[0]).toMatchObject({
      status: 'failed',
      errorMessage: 'Image moderation failed',
      rawError: 'Image moderation failed',
      retryable: true,
    });
  });

  it('prefers friendly error text while keeping raw error message for details', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          event_type: 'image_generation_failed',
          event_payload_json: {
            image_generation: true,
            friendly_error: 'The image service needs a clearer prompt.',
            error_message: 'provider returned 422: prompt_too_vague',
          },
        }),
      ],
      { now },
    );

    expect(groups[0].slots[0]).toMatchObject({
      status: 'failed',
      errorMessage: 'The image service needs a clearer prompt.',
      rawError: 'provider returned 422: prompt_too_vague',
    });
  });

  it('keeps separate image tasks on the same node in separate groups', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          id: 'task-a',
          event_type: 'image_generation_started',
          node_id: 'crew:visual',
          event_payload_json: {
            image_generation: true,
            task_id: 'hero-image',
            prompt_preview: 'Hero image',
          },
        }),
        event({
          id: 'task-b',
          event_type: 'image_generation_started',
          node_id: 'crew:visual',
          event_payload_json: {
            image_generation: true,
            task_id: 'detail-image',
            prompt_preview: 'Detail image',
          },
        }),
      ],
      { now },
    );

    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.taskId)).toEqual(['hero-image', 'detail-image']);
    expect(groups.map((group) => group.slots[0].promptPreview)).toEqual(['Hero image', 'Detail image']);
  });

  it('attaches a completion to the active slot with the matching prompt preview', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          id: 'start-a',
          event_type: 'image_generation_started',
          created_at: '2026-05-04T12:00:00Z',
          event_payload_json: {
            image_generation: true,
            prompt_preview: 'First prompt',
          },
        }),
        event({
          id: 'start-b',
          event_type: 'image_generation_started',
          created_at: '2026-05-04T12:00:01Z',
          event_payload_json: {
            image_generation: true,
            prompt_preview: 'Second prompt',
          },
        }),
        event({
          id: 'complete-b',
          event_type: 'image_generation_completed',
          created_at: '2026-05-04T12:00:05Z',
          event_payload_json: {
            image_generation: true,
            prompt_preview: 'Second prompt',
            artifact_id: 'artifact-second',
          },
        }),
      ],
      { now },
    );

    expect(groups[0].slots).toEqual([
      expect.objectContaining({ status: 'generating', promptPreview: 'First prompt' }),
      expect.objectContaining({ status: 'completed', promptPreview: 'Second prompt', artifactId: 'artifact-second' }),
    ]);
  });

  it('preserves completed slots when a later image fails', () => {
    const groups = buildImageProgressGroups(
      [
        event({
          id: 'complete-1',
          event_type: 'image_generation_completed',
          event_payload_json: {
            image_generation: true,
            artifact_id: 'artifact-1',
          },
        }),
        event({
          id: 'failed-2',
          event_type: 'image_generation_failed',
          event_payload_json: {
            image_generation: true,
            error_message: 'Provider timeout',
          },
        }),
      ],
      { now },
    );

    expect(groups[0].completedCount).toBe(1);
    expect(groups[0].slots).toEqual([
      expect.objectContaining({ status: 'completed', artifactId: 'artifact-1' }),
      expect.objectContaining({ status: 'failed', errorMessage: 'Provider timeout' }),
    ]);
  });
});
