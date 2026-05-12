import { fireEvent, render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { beforeEach, vi } from 'vitest';
import { appRoutes } from '../../src/app/routes';

vi.mock('../../src/features/settings/hooks', () => ({
  useSettingsShell: () => ({
    taskInputPresets: [
      {
        id: 'preset-1',
        key: 'website_url',
        label: '웹 사이트',
        inputType: 'url',
        description: '분석할 웹사이트 주소',
        isActive: true,
        sortOrder: 1,
      },
    ],
    isTaskInputPresetsLoading: false,
    taskInputPresetsError: null,
    refetchTaskInputPresets: vi.fn(),
  }),
}));

function renderAtPath(pathname: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [pathname] });
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
});

test('renders the build settings shell without credentials or execution bindings', () => {
  renderAtPath('/build/settings');

  expect(screen.getByRole('heading', { name: /^settings$/i })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { level: 2, name: /^credentials$/i })).not.toBeInTheDocument();
  expect(screen.queryByText(/runtime credentials are tracked here/i)).not.toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 2, name: /input presets/i })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { level: 3, name: /execution bindings/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /preset 추가/i })).not.toBeInTheDocument();
  expect(screen.getByText(/웹 사이트/i)).toBeInTheDocument();
  expect(screen.getByText(/active/i)).toBeInTheDocument();
});

test('reaches settings from the build navigation', () => {
  renderAtPath('/build/tasks');

  fireEvent.click(screen.getByRole('link', { name: /^settings$/i }));

  expect(screen.getByRole('heading', { name: /^settings$/i })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { level: 2, name: /^credentials$/i })).not.toBeInTheDocument();
});
