import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listTaskInputPresets } from '../../api/taskInputPresets';
import { queryKeys } from '../../hooks/queryKeys';

export type TaskInputPresetEntry = {
  id: string;
  key: string;
  label: string;
  inputType: string;
  description: string;
  isActive: boolean;
  sortOrder: number;
};

function normalizeString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

export function useSettingsShell() {
  const taskInputPresetsQuery = useQuery({
    queryKey: queryKeys.taskInputPresets.all(),
    queryFn: async () => {
      const rows = await listTaskInputPresets(true);
      return rows.map((row) => ({
        id: row.id,
        key: row.key,
        label: row.label,
        inputType: row.input_type,
        description: normalizeString(row.description),
        isActive: row.is_active,
        sortOrder: row.sort_order,
      })) satisfies TaskInputPresetEntry[];
    },
  });

  return useMemo(
    () => ({
      taskInputPresets: taskInputPresetsQuery.data ?? [],
      isTaskInputPresetsLoading: taskInputPresetsQuery.isLoading,
      taskInputPresetsError: taskInputPresetsQuery.error,
      refetchTaskInputPresets: taskInputPresetsQuery.refetch,
    }),
    [
      taskInputPresetsQuery.data,
      taskInputPresetsQuery.error,
      taskInputPresetsQuery.isLoading,
      taskInputPresetsQuery.refetch,
    ],
  );
}
