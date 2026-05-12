import { render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { beforeEach, vi } from 'vitest';
import { appRoutes } from '../../src/app/routes';

vi.mock('../../src/features/flows/hooks', async (importOriginal) => {
  const actual = (await importOriginal()) as typeof import('../../src/features/flows/hooks');

  return {
    ...actual,
    useFlowLibrary: () => ({
      flows: [
        {
          assetId: 'flow-1',
          versionId: 'flow-v1',
          versionNo: 1,
          name: 'Smoke Flow',
          description: 'Smoke-test flow',
          status: 'draft',
        },
      ],
      flowAssetsById: new Map(),
      isLoading: false,
      isError: false,
    }),
    usePublishedCrewsForFlow: () => ({
      publishedCrews: [],
      isLoading: false,
      isError: false,
    }),
    useLoadFlowDraft: () => ({
      mutateAsync: vi.fn().mockResolvedValue(null),
      isPending: false,
    }),
    useSaveFlowDraft: () => ({
      mutateAsync: vi.fn().mockResolvedValue({ draft: { id: 'draft-1' } }),
      isPending: false,
    }),
    useValidateFlowDraft: () => ({
      mutateAsync: vi.fn().mockResolvedValue({ schemaVersion: 1 }),
      isPending: false,
    }),
    usePublishFlowDraft: () => ({
      mutateAsync: vi.fn().mockResolvedValue({ version: { id: 'flow-v2' } }),
      isPending: false,
    }),
    useCreateFlow: () => ({
      mutateAsync: vi.fn().mockResolvedValue({ id: 'flow-created' }),
      isPending: false,
    }),
  };
});

function renderAtPath(pathname: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [pathname] });
  const result = render(<RouterProvider router={router} />);
  return { router, ...result };
}

beforeEach(() => {
  window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
});

const routes = [
  {
    path: '/',
    resolvedPath: '/home',
    heading: /^home$/i,
    copy: /Launch or select a run from the Run page/i,
  },
  {
    path: '/home',
    resolvedPath: '/home',
    heading: /^home$/i,
    copy: /Launch or select a run from the Run page/i,
  },
  {
    path: '/build/agents',
    resolvedPath: '/build/agents',
    heading: /^agents$/i,
    copy: /Build your agent library from versioned assets/i,
  },
  {
    path: '/build/tasks',
    resolvedPath: '/build/tasks',
    heading: /^tasks$/i,
    copy: /Create reusable task definitions with clear descriptions, expected outputs, and friendly preset inputs/i,
  },
  {
    path: '/build/crews',
    resolvedPath: '/build/crews',
    heading: /crew library/i,
    copy: /Pick a crew from the library to start drafting its runtime graph/i,
  },
  {
    path: '/build/flows',
    resolvedPath: '/build/flows',
    heading: /flow builder/i,
    copy: /Build, save, validate, and publish the active Flow graph/i,
  },
  {
    path: '/build/tools',
    resolvedPath: '/build/tools',
    heading: /^tools$/i,
    copy: /CrewAI and custom tools available for Agent and Task versions/i,
  },
  {
    path: '/build/credentials',
    resolvedPath: '/build/credentials',
    heading: /^credentials$/i,
    copy: /Connect provider API keys for CrewAI runs/i,
  },
  {
    path: '/build/settings',
    resolvedPath: '/build/settings',
    heading: /^settings$/i,
    copy: /Input presets and non-secret runtime setup/i,
  },
  {
    path: '/run',
    resolvedPath: '/run',
    heading: /^run$/i,
    copy: /Launch live workflow runs and review their output/i,
  },
  {
    path: '/run/streaming',
    resolvedPath: '/run/streaming',
    heading: /^streaming$/i,
    copy: /Follow the selected workflow run event timeline/i,
  },
  {
    path: '/run/io',
    resolvedPath: '/run/io',
    heading: /^i\/o$/i,
    copy: /Inspect the selected workflow run input, output, and latest state snapshot/i,
  },
] as const;

test('renders concrete feature pages for the primary frontend routes', async () => {
  for (const route of routes) {
    const { router, unmount } = renderAtPath(route.path);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: route.heading })).toBeInTheDocument();
    });
    expect(screen.getByText(route.copy)).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(route.resolvedPath);

    unmount();
  }
});
