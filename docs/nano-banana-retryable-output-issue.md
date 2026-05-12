# Nano Banana Retryable Output Issue

Date: 2026-05-04
Branch observed: `codex/google-sheets-agent-tool`

## Summary

Nano Banana image generation progress now exposes failed slots as `Retryable` when the backend classifies the provider error as transient, for example Google GenAI `503 UNAVAILABLE` or high-demand errors.

The UI currently only displays the `Retryable` state. It does not provide a retry button or a concrete retry action for that failed image slot.

Separately, successful `ax_nano_banana_image` tool calls return a very large artifact payload to the CrewAI agent. This includes storage backend details, Supabase public URLs, timestamps, full `metadata_json`, retention metadata, and duplicated fields. That payload is larger than what the agent needs for downstream tasks.

## Observed Behavior

### Retryable Without Action

In the Run page image progress panel:

- Slide 1: still generating, long-running
- Slide 2: completed
- Slide 3: failed
- Slide 3 displays `Retryable`
- No retry button is available

This is technically consistent with the current implementation: `retryable` is just event metadata, not an action contract.

### Verbose Tool Output

A successful Nano Banana tool result currently returns data shaped like:

- `artifact_id`
- `id`
- `run_id`
- `node_id`
- `artifact_type`
- `mime_type`
- `media_type`
- `sha256`
- `size_bytes`
- `storage_backend`
- `source_tool`
- `source_capability`
- `retention_mode`
- `expires_at`
- `retention_expires_at`
- `preview_url`
- `download_url`
- `status`
- full `metadata_json`
- `self_delete_supported`
- `created_at`
- `updated_at`
- duplicated `prompt_sha256`
- duplicated `prompt_length`
- `reused_existing_artifact`
- `model`
- `aspect_ratio`
- `image_size`

For an agent task, most of this is operational metadata, not reasoning input.

## Root Cause Notes

### Retryable Is a Classification, Not a Command

The backend event payload can classify a Nano Banana failure as retryable:

- `failure_kind: provider_unavailable`
- `retryable: true`
- `friendly_error: Temporary provider capacity issue`

The frontend progress model and panel read this metadata and display it.

There is no current per-image or per-tool retry endpoint attached to that slot. Existing retry behavior is primarily HITL-oriented:

- `HumanFeedbackDialog` has a `재시도` button.
- That path submits `needs_revision`.
- The backend then retries the previous crew through the HITL resume flow.

Image progress failures do not automatically create a pending HITL request, so the existing HITL retry button is not available for this case.

### Same-Run Reuse Only Helps If Retry Re-enters the Same Run/Node

The current artifact reuse logic is scoped to:

- same owner
- same run
- same node
- same prompt hash
- same model
- same aspect ratio
- same image size
- same artifact storage mode

This is good for cost control, but only if a retry executes inside the same run and same crew node context.

Starting a brand-new run will not reuse the previous run's generated image artifacts under the current design.

### Verbose Tool Output Is Not the Direct 503 Cause

The `503 UNAVAILABLE` / high-demand error comes from the Google image provider. The large tool output is not the direct cause of that provider capacity error.

However, the large output is still a real issue:

- It bloats the LLM observation/context after each image generation.
- It makes downstream agent reasoning noisier.
- It increases token usage.
- It may make subsequent task output formatting less stable.
- It exposes implementation details the agent does not need.

## Impact

### User Experience

The UI implies the failure can be retried, but gives no action. This is frustrating because the label reads like an affordance.

### Cost and Reliability

If the user restarts the whole flow manually, previously generated images may be generated again unless the retry path stays within the same run/node context.

### Agent Context Hygiene

Large image tool outputs can crowd out useful task context. For a carousel task, the agent usually only needs:

- `artifact_id`
- `preview_url` or `download_url`
- `mime_type`
- `model`
- `aspect_ratio`
- `image_size`
- `reused_existing_artifact`

It does not need full storage internals or duplicated metadata.

## Recommended Follow-Up Options

### Option A: Documentation/UI Copy Only

Change the label from `Retryable` to something like:

- `Temporary issue`
- `Retryable provider error`
- `Try rerunning this crew`

This avoids implying that a button exists. It is the smallest UX fix, but it does not solve the actual retry action.

### Option B: Add a Same-Run Crew Retry Action

Add an explicit backend endpoint that retries a failed crew node inside the same run.

Possible API shape:

```text
POST /api/flow-runs/{run_id}/retry-node
```

Request:

```json
{
  "node_id": "crew:c3bc0a2c-0825-41e2-8a83-02655ced8bd4",
  "reason": "retryable_image_generation_failure"
}
```

Expected behavior:

- Verify the run belongs to the current user.
- Verify the run is currently failed.
- Verify the target node is a crew node in the flow path.
- Load the latest run state snapshot.
- Set run status back to `running` or `executing`.
- Re-execute from the target node's path index.
- Preserve existing artifacts so same-run artifact reuse can skip already completed images.

This is the most useful product behavior, but it is a real runtime feature and needs careful tests.

### Option C: Create HITL Request on Retryable Tool Failure

When a retryable Nano Banana failure occurs, the runtime could create a pending human feedback request automatically.

Then the existing HITL `재시도` button could be used.

This reuses more existing UI, but semantically it is odd because the failure is not asking for human review of content. It is a provider capacity retry.

### Option D: Slim Nano Banana Tool Result

Keep full artifact metadata in the database, but return a compact tool result to CrewAI:

```json
{
  "artifact_id": "1032c185-2d8d-4242-b288-0ed77c009013",
  "mime_type": "image/jpeg",
  "preview_url": "https://...",
  "download_url": "https://...",
  "reused_existing_artifact": false,
  "model": "gemini-3.1-flash-image-preview",
  "aspect_ratio": "1:1",
  "image_size": "1K",
  "prompt_sha256": "051d...",
  "prompt_length": 396
}
```

This should reduce agent context pressure without changing artifact storage or Run page artifact display.

## Suggested Priority

1. Slim Nano Banana tool result.
2. Add UI copy that makes `Retryable` clearly informational until an action exists.
3. Design and implement same-run crew-node retry.

The retry button should not launch a new run if the goal is cost control. It should retry from the same run and same failed crew node so existing successful image artifacts can be reused.

