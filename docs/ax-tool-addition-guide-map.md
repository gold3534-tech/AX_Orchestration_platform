# AX Tool Addition Guide Map

Date: 2026-05-01

This guide is for agents and engineers adding new AX platform tools. It explains how to decide the capability type, which backend files usually need changes, what tests to add, and how to debug a tool that appears in the product but does not run correctly.

## Core Policy

AX exposes external abilities as `Capability` records at the product and policy layer.

AX has two capability types:

| Type | Meaning | Runtime surface |
| --- | --- | --- |
| `agent_tool` | A stable tool an Agent or Task may call while reasoning. AX-owned agent tools may also be exposed as explicit Tool Nodes when deterministic execution controls are needed. | CrewAI Agent/Task tool attachment, optional AX Tool Node |
| `Execution_Action` | A platform-managed action that needs explicit Flow placement, special lifecycle handling, approval/idempotency, artifact handling, or ongoing provider-specific maintenance. | Explicit Flow node executed by AX runtime |

Classification is not just "read vs write".

Use `agent_tool` when the tool is stable, bounded, and useful during agent reasoning. Creative and research tools usually belong here. Stable workspace operations can also belong here when scoped by explicit tool config.

Use `Execution_Action` when AX must own execution lifecycle, approval toggles, idempotency, auditability, durable external storage, publishing, or special provider maintenance risk.

Important runtime lesson:

> Attaching a tool to an Agent controls availability, not invocation count. If AX needs deterministic behavior, expose the AX-owned tool as an explicit Tool Node with node-level execution controls.

This does not create a third Capability Type. It creates a second runtime surface for selected `agent_tool` capabilities.

Current policy examples:

| Capability | Type | Implementation decision |
| --- | --- | --- |
| Google Sheets | `agent_tool` | AX custom tool using the official Google Sheets API. `append_rows` and `update_values` are controlled by boolean config. |
| Firecrawl | `agent_tool` | CrewAI built-in toolkit tool. Do not recreate unless AX needs unsupported Firecrawl operations. |
| Nano Banana image generation | `agent_tool` | AX custom creative tool using Google GenAI. Produces AX artifacts. Should be available as an AX Tool Node when users need `max_calls_per_node`, fixed output count, or official artifact selection. |
| Google Drive upload | `Execution_Action` | Explicit node. Uploads AX artifacts to user-owned Drive storage. |
| Instagram publish | `Execution_Action` | Explicit node. Provider setup, API churn, duplicate-publish risk, and audit needs require AX-managed lifecycle. |

## Decision Tree

1. Is there a reliable CrewAI toolkit tool that already covers the need?
   - Yes: prefer a `crewai.*` `agent_tool` catalog entry.
   - No: continue.

2. Does the capability need AX-specific credential ownership, artifact handling, structured output, or provider SDK control?
   - Yes: create an `ax.*` implementation.
   - No: a toolkit-backed `agent_tool` may be enough.

3. Does the capability publish, upload to durable external storage, require approval/idempotency, or need high-maintenance provider lifecycle handling?
   - Yes: use `Execution_Action`.
   - No: use `agent_tool`.

4. Is it a Google Workspace capability?
   - Use the official Google SDK directly.
   - Do not add LangChain Google Toolkit unless there is a new, explicit architecture decision reversing the current policy.

5. Does the tool produce user-visible files or images?
   - Create a `RunArtifact`.
   - Return structured artifact metadata with `artifact_id`, `preview_url`, `download_url`, and `storage_outcome`.
   - Do not place secrets, raw tokens, or sensitive provider URLs in public metadata.

6. Does the user need to control how many times the tool runs or which artifact becomes the official output?
   - Yes: expose the AX-owned `agent_tool` as an explicit AX Tool Node.
   - No: normal Agent/Task attachment is enough.

## Code Map

Use this map before editing. Most new tools do not need every file.

| Area | Files |
| --- | --- |
| Default tool catalog | `backend/api/services/default_crewai_tools.py` |
| Capability projection and policy | `backend/api/services/capabilities.py` |
| Provider metadata and tool credential requirements | `backend/api/runtime/credential_providers.py` |
| Custom AX CrewAI tools | `backend/api/tools/*.py` |
| Tool module allowlist and loading | `backend/api/runtime/tool_metadata.py`, `backend/api/runtime/tool_loader.py` |
| CrewAI assembly | `backend/api/runtime/crewai_factory.py` |
| Runtime credential injection | `backend/api/runtime/credential_resolver.py` |
| OAuth connected accounts | `backend/api/routes/connected_accounts.py`, `backend/api/services/connected_accounts.py`, `backend/api/runtime/oauth_clients.py` |
| Runtime graph snapshot | `backend/api/runtime/loaders/crew_graph_loader.py` |
| Flow execution | `backend/api/runtime/flow_snapshot_executor.py` |
| AX Tool Node execution | Future home should be near `backend/api/runtime/flow_snapshot_executor.py` or a dedicated `backend/api/runtime/tool_nodes.py` |
| Execution actions | `backend/api/runtime/execution_actions.py` |
| Artifact policy and public metadata | `backend/api/runtime/artifacts.py` |
| Run artifact content route | `backend/api/routes/runs.py` |
| Future AX managed file storage | Supabase Storage bucket integration is planned, but not part of the current MVP |
| DB models | `backend/api/db/models/*.py` |
| SQL migrations | `backend/sql/*.sql` |

## Adding An `agent_tool`

Use this path for stable Agent/Task-callable tools.

1. Choose the key.
   - CrewAI toolkit tools use `crewai.<tool_name>`.
   - AX-owned tools use `ax.<tool_name>`.

2. Decide credential shape.
   - API key providers are added to `SUPPORTED_CREDENTIAL_PROVIDERS` in `backend/api/runtime/credential_providers.py`.
   - OAuth providers should use connected accounts and `injection: "runtime_context"`.
   - Add the tool's requirement to `_TOOL_CREDENTIAL_REQUIREMENTS`.

3. Add or update the catalog entry.
   - For default tools, edit `backend/api/services/default_crewai_tools.py`.
   - Include `config_schema_json`, `input_schema_json`, `ui_schema_json`, and `credential_requirements`.
   - Tool config is where per-tool permissions belong, such as Google Sheets `append_rows_enabled` and `update_values_enabled`.

4. Implement the tool if AX owns it.
   - Put the class in `backend/api/tools/<tool_name>.py`.
   - Inherit from CrewAI `BaseTool`.
   - Use a Pydantic input schema.
   - Return structured JSON-compatible data.
   - Never log or return secrets.
   - Prefer official provider SDKs when AX owns credentials or output semantics.

5. Ensure the loader can instantiate it.
   - Confirm `backend/api/runtime/tool_metadata.py` allows the module path.
   - Confirm `backend/api/runtime/tool_loader.py` can import the class.

6. Confirm CrewAI runtime assembly.
   - Attached Agent/Task tools should appear in published snapshot fields such as `runtime_tools`, `agent_tool_links`, and `task_tool_links`.
   - `backend/api/runtime/crewai_factory.py` instantiates tools from that snapshot.

7. Add tests.
   - Catalog and metadata: `backend/tests/test_tooling_v2.py`
   - Capability projection: `backend/tests/test_capability_catalog_v2.py`
   - Factory assembly: `backend/tests/test_crewai_factory_v2.py`
   - Credential behavior: `backend/tests/test_runtime_credential_resolver_v2.py` or provider-specific tests
   - Tool behavior: create or extend a tool-specific test file

## Adding An AX Tool Node

Use this path when an AX-owned `agent_tool` needs explicit Flow placement and node-level controls, but does not fit the `Execution_Action` policy.

AX Tool Nodes are for deterministic tool execution. They are especially useful for artifact-producing tools such as image generation, where the platform must know exactly how many artifacts to create and which artifacts count as the node output.

This is a runtime surface, not a new Capability Type. The underlying capability remains `agent_tool`.

Recommended node config:

```json
{
  "tool_key": "ax.nano_banana_image",
  "max_calls_per_node": 1,
  "required": true,
  "on_call_limit": "return_existing",
  "official_output": "latest_artifact",
  "artifact_storage_mode": "temporary_only"
}
```

Field guidance:

- `tool_key`: the AX-owned tool to execute.
- `max_calls_per_node`: maximum allowed tool invocations for this node during one run. Default should be `1` for artifact-generating tools.
- `required`: when true, provider/auth/quota/tool failures should fail the node instead of becoming fallback prose.
- `on_call_limit`: recommended values are `return_existing`, `fail`, or `ignore`.
- `official_output`: recommended values are `latest_artifact`, `first_artifact`, or `all_artifacts`.
- `artifact_storage_mode`: tool-specific storage policy such as `temporary_only`.

Runtime rules:

- The node should call the tool directly instead of asking an LLM to decide whether to call it.
- The node should record every generated artifact, but return only the official output according to `official_output`.
- If the tool is also attached to an Agent in the same flow, node-level call limits should be independent from Agent-call limits.
- For deterministic flows, prefer Tool Nodes over prompt instructions like "generate exactly one image".
- Tool Node outputs should be structured JSON, never only natural-language text.

Current observed issue:

- Run `97fb184a-0757-4539-b12f-c9f0e40d78a0` generated 3 artifacts because CrewAI called `ax_nano_banana_image` 3 times inside one Agent/Task node.
- The Nano Banana tool itself generated 1 image per call; the extra images came from repeated tool invocation.
- This confirms the need for `max_calls_per_node` and explicit AX Tool Nodes for artifact-producing tools.

Suggested tests:

- Node configured with `max_calls_per_node: 1` creates one artifact even if an Agent would otherwise iterate.
- Node configured with `required: true` fails on provider quota/auth errors.
- Node output includes `artifact_id`, `preview_url`, `download_url`, and `storage_outcome`.
- Run detail exposes official artifacts without relying on the Agent's final text.

## Adding An `Execution_Action`

Use this path for explicit Flow nodes that AX must control.

1. Add the capability contract.
   - Edit `EXECUTION_ACTIONS` in `backend/api/services/capabilities.py`.
   - Include `input_schema`, `config_schema`, `output_schema`, `supported_approval_modes`, `approval_policy`, `risk_level`, `provider`, and `auth_type`.

2. Add the executor.
   - Edit `backend/api/runtime/execution_actions.py`.
   - Add a function that accepts `ExecutionActionRequest` and returns structured output.
   - Register it with `register_execution_action`.

3. Make execution safe.
   - Use `artifact_id` inputs for AX-created files.
   - Enforce owner checks through existing artifact helpers.
   - Keep idempotency stable for duplicate run protection.
   - Respect `approval_mode`; explicit nodes may allow approval On/Off.

4. Resolve credentials at runtime.
   - OAuth actions should build provider clients from connected accounts.
   - Do not expose OAuth tokens to the frontend.
   - Do not inject OAuth tokens into agent prompts.

5. Add tests.
   - Generic action behavior: `backend/tests/test_execution_actions_v2.py`
   - Provider-specific action behavior: for example `backend/tests/test_google_drive_action_v2.py`
   - Flow skeleton or runtime integration if the action affects graph execution.

## OAuth And Credentials

Supabase Auth identifies the AX user. Provider credentials authorize external tools and actions.

API key credentials:

- Are stored through the credential store.
- Are resolved into runtime environment variables for live runs.
- Are suitable for providers like Serper, Firecrawl, OpenAI, and Google Gemini API-key usage.

OAuth connected accounts:

- Are user-specific provider grants.
- Are stored as connected credentials with `auth_type = "oauth2"`.
- Should track provider account metadata, scopes, status, and refresh behavior.
- Are resolved only inside backend runtime code.
- Must not be returned to the frontend or injected into prompts.

Google Workspace policy:

- Sheets and Drive share `google_workspace` connected account infrastructure.
- Sheets is still an `agent_tool`.
- Drive upload is still an `Execution_Action`.
- Both should use official Google SDKs directly.

Google Gemini image policy:

- The default Nano Banana 2 model is `gemini-3.1-flash-image-preview`.
- Nano Banana Pro is `gemini-3-pro-image-preview` and should be treated as a separate model option because project access and quota may differ.
- The legacy Nano Banana model is `gemini-2.5-flash-image`.
- A `429 RESOURCE_EXHAUSTED` with a quota limit of `0` usually means the selected project/model/tier has no usable quota, not that AX failed to attach the tool.

## Artifacts

Any image or file-producing tool should use AX artifact metadata.

Rules:

- Create a `RunArtifact` for user-visible generated files.
- Use `temporary` or `ax_managed` storage for AX-hosted bytes.
- Use `google_drive` storage only when the user explicitly sends the artifact to Drive.
- MVP retention defaults to 7 days for AX-managed or temporary artifacts.
- User self-delete is not part of the MVP.
- Public metadata may include safe URLs such as `/api/run-artifacts/<artifact_id>/content`.
- Public metadata must not include access tokens, refresh tokens, API keys, authorization headers, credential IDs, or secret-like URLs.

Current MVP storage behavior:

- Generated image bytes are written to local temporary storage.
- The default local path is `<system temp>/ax-artifacts` unless `AX_ARTIFACT_STORAGE_ROOT` is configured.
- Artifact metadata is stored in the database through `run_artifacts`.
- Browser rendering fetches `/api/run-artifacts/<artifact_id>/content` with bearer auth and creates a temporary browser Blob URL.
- Browser Blob URLs are only for preview rendering. They are not durable storage and are not Supabase Storage objects.
- Supabase Storage buckets are not used by the current MVP. Seeing `+ New bucket` in Supabase Storage is expected.

Current run output rendering behavior:

- The Run page does not rely on the Agent's final natural-language answer to discover generated artifacts.
- `GET /api/flow-runs/<run_id>` returns an `artifacts` array by querying `run_artifacts` for the run and owner.
- The Run page prioritizes that `artifacts` array before falling back to `output_json` or the latest node output.
- `OutputPreview` recognizes safe `preview_url` and `download_url` values such as `/api/run-artifacts/<artifact_id>/content`.
- Internal artifact URLs are fetched with bearer auth, then rendered through browser Blob URLs.
- Therefore users should not need to write Task Expected Output instructions like "final answer must only include artifact_id and image metadata" for the Run page to render generated images.
- This is not final-answer parsing. It is backend artifact metadata lookup plus frontend artifact preview rendering.
- Current caveat: the I/O page output preview still passes only `run.output_json` to `OutputPreview`, so it may not show artifacts that the Run page can render. Keep these pages aligned when touching run output UX.

Future AX Managed Storage plan:

- Keep the MVP behavior as-is until product storage policy is ready.
- Introduce a Supabase Storage bucket for `ax_managed` artifacts.
- Keep `temporary` artifacts on short-lived local or worker-local storage.
- Preserve `run_artifacts` as the metadata and access-control source of truth.
- Store only provider-safe paths/object keys in metadata; do not expose bucket service keys or signed URLs with secret query parameters.
- Add a retention worker for expiry cleanup.
- Add paid-plan retention tiers later: default 7 days, then 30/90 days by plan.
- User self-delete remains out of MVP and should be added as a later explicit product feature.

Recommended tool output shape:

```json
{
  "artifact_id": "uuid",
  "artifact_type": "image",
  "mime_type": "image/png",
  "preview_url": "/api/run-artifacts/<artifact_id>/content",
  "download_url": "/api/run-artifacts/<artifact_id>/content",
  "storage_outcome": "temporary_only"
}
```

## Required Tool Behavior

Attaching an `agent_tool` does not guarantee that an LLM agent will call it. If a flow must produce an image, spreadsheet write, or other concrete side effect, encode that requirement in business logic.

Current guidance:

- Use dedicated Tasks and clear expected outputs for tool-dependent work.
- Use AX Tool Nodes when the platform must control invocation count or official artifact output.
- Add `max_calls_per_node` for artifact-producing tool nodes. Default to `1` unless the node explicitly supports variants.
- Inspect run events for `tool_execution_started`, `tool_execution_completed`, and `tool_execution_failed`.
- Treat provider quota, auth, and permission failures as structured runtime failures when the generation is required.
- Do not accept a natural-language fallback like "I could not generate the image" as a successful required generation result.

This is especially important for image generation. A Nano Banana provider quota error can still lead the agent to complete with fallback text unless AX marks the tool-dependent task or run as failed.

It is also important for successful image generation. A single run can produce multiple artifacts if the Agent calls the image tool repeatedly. The tool's default is not necessarily the output count; the call count is controlled by CrewAI unless AX adds a Tool Node or runtime call limit.

## Troubleshooting Map

Tool is not visible in the UI:

- Check `/api/tool-catalog`.
- Check `backend/api/services/default_crewai_tools.py`.
- Check `backend/api/services/capabilities.py`.
- Check credential provider metadata if the UI filters by provider or auth type.

Tool is visible but cannot be attached:

- Check capability fields `is_attachable` and `is_runtime_available`.
- Check whether the tool exists only as a planned capability.

Tool is attached but missing at runtime:

- Check `version_tools`.
- Check published snapshot fields `runtime_tools`, `agent_tool_links`, and `task_tool_links`.
- Check `backend/api/runtime/loaders/crew_graph_loader.py`.
- Check `backend/api/runtime/crewai_factory.py`.

Tool is loaded but not called:

- Check Agent role/goal/backstory and Task description/expected output.
- Check whether the Task has the tool or only the Agent has it.
- Check run events before assuming the backend failed.
- For deterministic side effects, add business logic rather than relying on agent discretion.

Tool produces too many artifacts:

- Check run events for repeated `tool_execution_started` / `tool_execution_completed` pairs.
- Check `run_artifacts` grouped by `run_id` and `node_id`.
- If a single Agent/Task node produced several artifacts, use an AX Tool Node with `max_calls_per_node`.
- If one tool call produced several artifacts, add a tool config such as `number_of_images` and enforce its bounds.

Tool is called but fails:

- Inspect `tool_execution_failed` events.
- Check credential status and provider quota.
- Check runtime environment variables for API-key providers.
- Check connected account state and scopes for OAuth providers.
- Check provider-specific SDK error payloads.

Artifact exists but preview fails:

- Check `run_artifacts.status`.
- Check `storage_backend`, `storage_path`, and `metadata_json.preview_url`.
- Check `GET /api/run-artifacts/<artifact_id>/content`.
- If the endpoint requires bearer auth, a plain browser image tag is not enough; the frontend must fetch with auth and render a blob URL.
- Check whether the failing screen uses `run.artifacts`. The Run page currently includes artifacts in its preview input; the I/O page output preview may only inspect `run.output_json`.
- Do not debug this as an Expected Output prompt issue unless no `RunArtifact` row was created.

Execution action duplicates or stalls:

- Check `execution_action_runs.idempotency_key`.
- Check `approval_mode`.
- Check pending human feedback rows.
- Check whether the previous action run already succeeded.

## Do Not

- Do not add LangChain wrappers around Google Workspace tools under the current policy.
- Do not reimplement CrewAI toolkit tools unless AX needs behavior the toolkit does not support.
- Do not classify every write as `Execution_Action`; stable, bounded tool writes may remain `agent_tool`.
- Do not classify high-maintenance publish/storage actions as flexible `agent_tool`.
- Do not expose OAuth tokens or API keys in tool outputs, events, metadata, or frontend payloads.
- Do not rely on ORM `create_all` for production schema changes; add SQL migrations.
- Do not assume tool attachment means tool invocation.
- Do not assume one run means one tool call. Agent reasoning loops may call the same tool several times.
- Do not rely on prompt wording alone to limit artifact count when the product needs a deterministic result.

## Minimal PR Checklist

Before handing off a new tool:

- The capability type decision is documented.
- The tool/action appears in the catalog or capability endpoint as intended.
- Credential requirements are explicit.
- Runtime loading is covered by tests.
- Provider calls are mocked in tests.
- Tool outputs are structured and do not leak secrets.
- Artifact producers create `RunArtifact` rows.
- Artifact-producing AX tools document whether they support Agent attachment only, Tool Node execution, or both.
- Tool Node configs include sensible call limits such as `max_calls_per_node`.
- Execution actions have approval/idempotency tests.
- A manual run was inspected through run events, not only final output text.
