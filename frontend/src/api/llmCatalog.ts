import { client } from './client';

export type LLMModelCatalogItem = {
  model_key: string;
  provider_key: string;
  display_name: string;
  enabled: boolean;
  sort_order: number;
  llm_metadata_json: Record<string, unknown>;
};

export type LLMProviderCatalogItem = {
  provider_key: string;
  display_name: string;
  provider_type: 'hosted' | 'local';
  credential_provider?: string | null;
  enabled: boolean;
  sort_order: number;
  metadata_json: Record<string, unknown>;
  models: LLMModelCatalogItem[];
};

export type LLMCatalogResponse = {
  providers: LLMProviderCatalogItem[];
};

export async function getLlmCatalog(): Promise<LLMCatalogResponse> {
  const { data, error } = await client.GET('/api/llm-catalog' as never);

  if (error) {
    throw error;
  }

  return data as LLMCatalogResponse;
}
