import { useQuery } from '@tanstack/react-query';
import { getToolCatalog } from '../../api/tooling';
import { queryKeys } from '../../hooks/queryKeys';
import type { components } from '../../types/api.generated';

type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];

type MutationResult<TData> = {
  data?: TData;
  error?: unknown;
};

function unwrapQueryResult<TData>({ data, error }: MutationResult<TData>) {
  if (error) {
    throw error;
  }

  return data;
}

function mapToolCatalogEntry(tool: ToolCatalogResponse) {
  return {
    key: tool.tool_key,
    name: tool.name,
    status: tool.enabled ? 'Enabled' : 'Disabled',
    summary: tool.description || `${tool.module_path}.${tool.class_name}`,
    type: tool.tool_type,
  };
}

export function useToolLibrary() {
  const query = useQuery({
    queryKey: queryKeys.tooling.toolCatalog(),
    queryFn: async () => {
      const tools = unwrapQueryResult(await getToolCatalog()) ?? [];
      return tools.map(mapToolCatalogEntry);
    },
  });

  return {
    tools: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
