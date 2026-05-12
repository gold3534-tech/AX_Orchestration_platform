export type ImageProgressSlotStatus = 'generating' | 'completed' | 'failed';

export type ImageProgressSlot = {
  index: number;
  status: ImageProgressSlotStatus;
  promptPreview?: string;
  artifactId?: string;
  previewUrl?: string;
  mimeType?: string;
  errorMessage?: string;
  rawError?: string;
  retryable?: boolean;
  startedAt?: string;
  completedAt?: string;
  elapsedMs?: number;
  matchKeys?: string[];
};

export type ImageProgressGroup = {
  groupId: string;
  nodeId: string | null;
  taskId: string | null;
  completedCount: number;
  totalCount: number;
  slots: ImageProgressSlot[];
};

type ImageProgressEvent = Record<string, unknown>;

type BuildOptions = {
  now?: Date;
};

type GroupDraft = {
  groupId: string;
  nodeId: string | null;
  taskId: string | null;
  totalCount: number;
  slots: ImageProgressSlot[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function payloadRecord(event: ImageProgressEvent) {
  return isRecord(event.event_payload_json) ? event.event_payload_json : {};
}

function stringValue(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function booleanValue(value: unknown) {
  return typeof value === 'boolean' ? value : undefined;
}

function firstString(...values: unknown[]) {
  for (const value of values) {
    const text = stringValue(value);
    if (text) return text;
  }
  return undefined;
}

function toolName(event: ImageProgressEvent, payload: Record<string, unknown>) {
  return firstString(payload.tool, payload.tool_name, payload.toolName, payload.name, event.tool, event.tool_name) ?? '';
}

function isNanoBananaTool(name: string) {
  const normalized = name.toLowerCase().replace(/[^a-z0-9]+/g, '');
  return normalized.includes('nano') && normalized.includes('banana');
}

function isImageGenerationEvent(event: ImageProgressEvent) {
  const payload = payloadRecord(event);
  return payload.image_generation === true || isNanoBananaTool(toolName(event, payload));
}

function eventType(event: ImageProgressEvent) {
  return stringValue(event.event_type)?.toLowerCase() ?? '';
}

function statusFromEvent(event: ImageProgressEvent): ImageProgressSlotStatus {
  const payload = payloadRecord(event);
  const type = eventType(event);
  const status = stringValue(payload.status)?.toLowerCase() ?? '';
  if (
    type.includes('fail') ||
    type.includes('error') ||
    status === 'failed' ||
    status === 'error' ||
    status === 'cancelled'
  ) {
    return 'failed';
  }
  if (
    type.includes('complete') ||
    type.includes('success') ||
    status === 'completed' ||
    status === 'succeeded' ||
    status === 'success'
  ) {
    return 'completed';
  }
  return 'generating';
}

function groupFields(event: ImageProgressEvent, payload: Record<string, unknown>) {
  const nodeId = firstString(event.node_id, payload.node_id, payload.crew_node_id, payload.source_node_id) ?? null;
  const taskId = firstString(event.task_id, payload.task_id, payload.task_name, payload.task) ?? null;
  const tool = toolName(event, payload) || null;
  const groupParts = [nodeId, taskId].filter((value): value is string => Boolean(value));
  return {
    nodeId,
    taskId,
    groupId: groupParts.length > 0 ? groupParts.join('::') : tool ?? 'image-generation',
  };
}

function totalCount(payload: Record<string, unknown>) {
  return (
    numberValue(payload.total_count) ??
    numberValue(payload.totalCount) ??
    numberValue(payload.image_count) ??
    numberValue(payload.imageCount) ??
    numberValue(payload.n) ??
    3
  );
}

function nestedArtifact(payload: Record<string, unknown>) {
  return isRecord(payload.artifact) ? payload.artifact : {};
}

function promptPreview(payload: Record<string, unknown>) {
  const toolInput = payload.tool_input;
  if (isRecord(toolInput)) {
    return firstString(
      payload.prompt_preview,
      payload.promptPreview,
      payload.prompt,
      payload.revised_prompt,
      toolInput.prompt,
      toolInput.description,
    );
  }

  return firstString(
    payload.prompt_preview,
    payload.promptPreview,
    payload.prompt,
    payload.revised_prompt,
    typeof toolInput === 'string' && toolInput.length <= 240 ? toolInput : null,
  );
}

function errorText(error: unknown) {
  if (typeof error === 'string') return error;
  if (error === undefined || error === null) return undefined;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function imageFields(payload: Record<string, unknown>) {
  const artifact = nestedArtifact(payload);
  const rawError = errorText(payload.error_message ?? payload.errorMessage ?? payload.error ?? payload.raw_error ?? payload.rawError);
  return {
    promptPreview: promptPreview(payload),
    artifactId: firstString(payload.artifact_id, payload.artifactId, artifact.id, artifact.artifact_id),
    previewUrl: firstString(
      payload.preview_url,
      payload.previewUrl,
      payload.image_url,
      payload.url,
      artifact.preview_url,
      artifact.download_url,
    ),
    mimeType: firstString(payload.mime_type, payload.mimeType, artifact.mime_type, artifact.mimeType),
    errorMessage: firstString(payload.friendly_error, payload.friendlyError, payload.error_message, payload.errorMessage, payload.message) ?? rawError,
    rawError,
    retryable: booleanValue(payload.retryable),
    matchKeys: matchKeys(payload),
  };
}

function createdAt(event: ImageProgressEvent) {
  return stringValue(event.created_at) ?? stringValue(event.timestamp) ?? undefined;
}

function timestampMs(value: string | undefined) {
  if (!value) return null;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}

function elapsedMs(slot: ImageProgressSlot, payload: Record<string, unknown>, now: Date) {
  const provided = numberValue(payload.elapsed_ms) ?? numberValue(payload.elapsedMs) ?? numberValue(payload.duration_ms);
  if (provided !== null) return provided;

  const started = timestampMs(slot.startedAt);
  if (started === null) return undefined;
  const ended = timestampMs(slot.completedAt) ?? now.getTime();
  return Math.max(0, ended - started);
}

function firstGeneratingSlot(slots: ImageProgressSlot[]) {
  return slots.find((slot) => slot.status === 'generating');
}

function uniqueStrings(values: Array<string | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

function matchKeys(payload: Record<string, unknown>) {
  return uniqueStrings([
    payload.image_generation_id,
    payload.imageGenerationId,
    payload.generation_id,
    payload.generationId,
    payload.invocation_id,
    payload.invocationId,
    payload.tool_call_id,
    payload.toolCallId,
    payload.request_id,
    payload.requestId,
    payload.id,
    promptPreview(payload),
  ].map((value) => firstString(value)));
}

function matchingGeneratingSlot(slots: ImageProgressSlot[], payload: Record<string, unknown>) {
  const keys = matchKeys(payload);
  if (keys.length > 0) {
    const matched = slots.find(
      (slot) => slot.status === 'generating' && slot.matchKeys?.some((slotKey) => keys.includes(slotKey)),
    );
    if (matched) return matched;
  }

  // Without a stable payload signal, terminal events are paired to the earliest active slot in event order.
  return firstGeneratingSlot(slots);
}

function mergeDefined<T extends Record<string, unknown>>(target: T, fields: Record<string, unknown>) {
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined) {
      target[key as keyof T] = value as T[keyof T];
    }
  }
}

function applyTerminalEvent(
  slots: ImageProgressSlot[],
  status: ImageProgressSlotStatus,
  payload: Record<string, unknown>,
  eventTime: string | undefined,
  now: Date,
) {
  const slot = status === 'generating' ? undefined : matchingGeneratingSlot(slots, payload);
  const target =
    slot ??
    ({
      index: slots.length,
      status,
    } satisfies ImageProgressSlot);

  if (!slot) {
    slots.push(target);
  }

  target.status = status;
  if (status === 'generating') {
    target.startedAt = eventTime;
  } else if (status === 'completed' || status === 'failed') {
    target.startedAt ??= eventTime;
    target.completedAt = eventTime;
  }

  mergeDefined(target, imageFields(payload));
  target.elapsedMs = elapsedMs(target, payload, now);
}

export function buildImageProgressGroups(events: ImageProgressEvent[], options: BuildOptions = {}): ImageProgressGroup[] {
  const now = options.now ?? new Date();
  const groups = new Map<string, GroupDraft>();

  for (const event of events) {
    if (!isImageGenerationEvent(event)) continue;

    const payload = payloadRecord(event);
    const fields = groupFields(event, payload);
    const existing = groups.get(fields.groupId);
    const group =
      existing ??
      ({
        ...fields,
        totalCount: 3,
        slots: [],
      } satisfies GroupDraft);

    group.totalCount = Math.max(group.totalCount, totalCount(payload), group.slots.length);
    groups.set(group.groupId, group);
    applyTerminalEvent(group.slots, statusFromEvent(event), payload, createdAt(event), now);
    group.totalCount = Math.max(group.totalCount, group.slots.length, 3);
  }

  return Array.from(groups.values()).map((group) => ({
    ...group,
    completedCount: group.slots.filter((slot) => slot.status === 'completed').length,
  }));
}
