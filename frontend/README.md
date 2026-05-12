# AI Oh Frontend

This package is the React frontend shell for AI Oh.

## What Lives Here

- `src/app/routes.tsx` owns routing and auth gating.
- `src/api/*` is the only backend HTTP boundary.
- `src/features/<domain>/*` owns page-level UI, page-specific state, and feature workflows.
- `src/components/*` holds shared layout and platform primitives.
- `src/types/api.generated.ts` is generated contract data and should be updated from `docs/openapi.json`, not hand-edited.

## Route Surface

- `/` redirects to `/build/agents` when authenticated and `/login` otherwise.
- `/login`
- `/auth/callback`
- `/build/agents`
- `/build/tasks`
- `/build/crews`
- `/build/flows`
- `/build/flows/:flowId`
- `/build/tools`
- `/build/credentials`
- `/build/settings`
- `/run`
- `/run/streaming`
- `/run/io`
- Unknown URLs stay inside the shell with a visible not-found state.

## Frontend Boundaries

- Keep HTTP requests, response unwrapping, and backend error parsing in `src/api/*`.
- Keep React Query calls and domain data mapping in `src/features/<domain>/hooks.ts`.
- Keep builder canvases in `src/features/crews/*Canvas.tsx` and `src/features/flows/*Canvas.tsx`.
- Keep shared dialogs, buttons, and forms in `src/components/shared`.
- Keep shell, navigation, and framing in `src/components/layout`.
- Regenerate `src/types/api.generated.ts` from the OpenAPI snapshot whenever the backend contract changes.

## Current Shell Status

- The navigation shell is wired and the main build/run routes resolve to concrete feature pages.
- `/build/flows` remains the default flow library entry point.
- Feature workflows, live graph editing polish, and execution behavior continue to live in the feature folders and tests.

## Working Notes

- Keep feature changes inside the owning `src/features/<domain>` folder when possible.
- Use the shared shell for navigation, framing, and cross-cutting layout only.
- When adding or updating API calls, keep them in `src/api/*` so the backend contract stays isolated from the UI.
- Frontend smoke tests live under `frontend/tests/smoke`.
