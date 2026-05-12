import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { beforeEach, vi, expect, test } from 'vitest';
import { appRoutes } from '../../src/app/routes';

vi.mock('../../src/features/tasks/hooks', () => ({
  useTasksLibrary: () => ({
    tasks: [
      {
        assetId: 'task-1',
        versionId: 'task-v1',
        name: 'Custom Task',
        description: 'Custom task summary {custom_a}',
        expectedOutput: 'Custom output {custom_a}',
        inputPresets: ['custom_a'],
        tools: [],
        summary: 'Custom task summary',
        status: 'Draft',
      },
    ],
    inputPresets: [
      { label: 'Custom preset A', key: 'custom_a', inputType: 'text', description: 'Custom description A' },
      { label: 'Custom preset B', key: 'custom_b', inputType: 'text', description: 'Custom description B' },
    ],
    tools: ['Web Search'],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    presetCatalogError: null,
    isPresetCatalogLoading: false,
    refetchPresetCatalog: vi.fn(),
  }),
  useCreateTask: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateTask: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteTask: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function renderAtPath(pathname: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [pathname] });
  render(<RouterProvider router={router} />);
}

beforeEach(() => {
  window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
});

test('renders task presets from the tasks library hook into the task form', () => {
  renderAtPath('/build/tasks');
  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));

  expect(screen.getByRole('option', { name: /custom preset a/i })).toBeInTheDocument();
  expect(screen.getByRole('option', { name: /custom preset b/i })).toBeInTheDocument();
  expect(screen.queryByText('웹 사이트')).not.toBeInTheDocument();
});

test('defaults task inspector preset insertion to description after focus leaves an eligible field', () => {
  renderAtPath('/build/tasks');

  fireEvent.click(screen.getByText('Custom Task'));
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

  const expectedOutput = screen.getByLabelText(/expected output/i);
  fireEvent.focus(expectedOutput);
  fireEvent.focus(screen.getByLabelText(/name/i));
  fireEvent.change(screen.getByLabelText(/input presets/i), { target: { value: 'custom_b' } });

  expect(screen.getByRole('textbox', { name: /^description$/i })).toHaveValue('Custom task summary {custom_a} {custom_b}');
  expect(expectedOutput).toHaveValue('Custom output {custom_a}');
});

test('keeps expected output as task inspector preset target when the select receives focus', () => {
  renderAtPath('/build/tasks');

  fireEvent.click(screen.getByText('Custom Task'));
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

  const expectedOutput = screen.getByLabelText(/expected output/i);
  const presetSelect = screen.getByLabelText(/input presets/i);

  fireEvent.focus(expectedOutput);
  fireEvent.focus(presetSelect);
  fireEvent.change(presetSelect, { target: { value: 'custom_b' } });

  expect(screen.getByRole('textbox', { name: /^description$/i })).toHaveValue('Custom task summary {custom_a}');
  expect(expectedOutput).toHaveValue('Custom output {custom_a} {custom_b}');
});

test('defaults task inspector preset insertion after focus moves from expected output to tool picker', () => {
  renderAtPath('/build/tasks');

  fireEvent.click(screen.getByText('Custom Task'));
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));

  const expectedOutput = screen.getByLabelText(/expected output/i);
  fireEvent.focus(expectedOutput);
  fireEvent.focus(screen.getByLabelText(/tool to add/i));
  fireEvent.change(screen.getByLabelText(/input presets/i), { target: { value: 'custom_b' } });

  expect(screen.getByRole('textbox', { name: /^description$/i })).toHaveValue('Custom task summary {custom_a} {custom_b}');
  expect(expectedOutput).toHaveValue('Custom output {custom_a}');
});

test('removes task preset token from inspector body fields when removing a preset', () => {
  renderAtPath('/build/tasks');

  fireEvent.click(screen.getByText('Custom Task'));
  fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
  fireEvent.click(screen.getByRole('button', { name: /remove/i }));

  expect(screen.getByRole('textbox', { name: /^description$/i })).toHaveValue('Custom task summary');
  expect(screen.getByLabelText(/expected output/i)).toHaveValue('Custom output');
});
