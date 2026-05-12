import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { listTaskInputPresets } from '../../src/api/taskInputPresets';
import { useSettingsShell } from '../../src/features/settings/hooks';

vi.mock('../../src/api/taskInputPresets', () => ({
  listTaskInputPresets: vi.fn(),
}));

test('loads task input presets into the settings shell data contract', async () => {
  vi.mocked(listTaskInputPresets).mockResolvedValue([
    {
      id: 'preset-1',
      key: 'website_url',
      label: '웹 사이트',
      input_type: 'url',
      description: '분석할 웹사이트 주소',
      is_active: true,
      sort_order: 1,
    },
  ]);

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
  );

  const { result } = renderHook(() => useSettingsShell(), { wrapper });

  await waitFor(() => {
    expect(result.current.taskInputPresets[0]).toMatchObject({
      key: 'website_url',
      label: '웹 사이트',
      inputType: 'url',
    });
  });
  expect(result.current).not.toHaveProperty('credentials');
  expect(result.current).not.toHaveProperty('executionBindings');
  expect(result.current).not.toHaveProperty('createTaskInputPreset');
  expect(result.current).not.toHaveProperty('toggleTaskInputPresetActive');
});
