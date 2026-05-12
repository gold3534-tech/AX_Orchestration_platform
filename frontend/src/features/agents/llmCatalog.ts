import type { LLMCatalogResponse } from '../../api/llmCatalog';

export type LLMParameterSpec = {
  supported?: boolean;
  min?: number;
  max?: number;
  default?: number;
};

export type LLMModelOption = {
  value: string;
  label: string;
  providerKey: string;
  providerLabel: string;
  metadata: Record<string, unknown>;
};

type ParameterName = 'temperature' | 'max_tokens';

function asRecord(value: unknown) {
  return value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function asOptionalString(value: unknown) {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function asOptionalNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function sortByOrder<T extends { sort_order: number }>(items: T[]) {
  return [...items].sort((left, right) => left.sort_order - right.sort_order);
}

export function modelOptionsFromCatalog(catalog?: LLMCatalogResponse): LLMModelOption[] {
  return sortByOrder(catalog?.providers ?? []).flatMap((provider) =>
    sortByOrder(provider.models).map((model) => ({
      value: model.model_key,
      label: `${model.display_name} · ${provider.display_name}`,
      providerKey: provider.provider_key,
      providerLabel: provider.display_name,
      metadata: model.llm_metadata_json,
    })),
  );
}

export function findModelOption(options: LLMModelOption[], modelKey: string | undefined) {
  return options.find((option) => option.value === modelKey);
}

export function parameterSpec(modelOption: LLMModelOption | undefined, parameter: ParameterName): LLMParameterSpec | undefined {
  const parameters = asRecord(modelOption?.metadata.parameters);
  const spec = asRecord(parameters[parameter]);

  if (Object.keys(spec).length === 0) {
    return undefined;
  }

  return {
    supported: typeof spec.supported === 'boolean' ? spec.supported : undefined,
    min: asOptionalNumber(spec.min),
    max: asOptionalNumber(spec.max),
    default: asOptionalNumber(spec.default),
  };
}

export function isParameterSupported(modelOption: LLMModelOption | undefined, parameter: ParameterName) {
  return parameterSpec(modelOption, parameter)?.supported === true;
}

export function numericDefault(modelOption: LLMModelOption | undefined, parameter: ParameterName) {
  return parameterSpec(modelOption, parameter)?.default;
}

export function inferProviderFromModelOption(options: LLMModelOption[], modelKey: string | undefined) {
  return findModelOption(options, modelKey)?.providerKey;
}

export function legacyModelString(value: unknown) {
  if (typeof value === 'string') {
    return value;
  }

  const payload = asRecord(value);

  return asOptionalString(payload.main_model) ?? asOptionalString(payload.model);
}

export function legacyProviderString(value: unknown) {
  return asOptionalString(asRecord(value).provider);
}

export function legacyNumber(value: unknown, key: ParameterName) {
  return asOptionalNumber(asRecord(value)[key]);
}
