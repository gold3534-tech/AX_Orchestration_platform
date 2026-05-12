import { client } from './client';

export const CAPABILITY_TYPES = ['agent_tool', 'Execution_Action'] as const;

export type CapabilityType = (typeof CAPABILITY_TYPES)[number];

export type JsonSchemaObject = {
  type?: string;
  properties?: Record<string, unknown>;
  required?: string[];
  enum?: string[];
  default?: unknown;
  additionalProperties?: boolean | Record<string, unknown>;
  [key: string]: unknown;
};

export type CapabilityCatalogItem = {
  key: string;
  type: CapabilityType;
  label: string;
  description: string;
  implementation_status: 'available' | 'planned';
  is_attachable: boolean;
  is_runtime_available: boolean;
  provider: string | null;
  auth_type: string;
  required_scopes: string[];
  required_account_status: string;
  input_schema: JsonSchemaObject;
  config_schema: JsonSchemaObject;
  output_schema: JsonSchemaObject;
  supported_approval_modes: string[];
  approval_policy: Record<string, unknown>;
  risk_level: 'read' | 'write' | 'upload' | 'publish';
  artifact_input_requirements: Record<string, unknown>;
  implementation: string;
  policy_rationale: string;
};

type ApiResult<TData> = {
  data?: TData;
  error?: unknown;
  response: Response;
};

export function listCapabilities() {
  return client.GET('/api/capabilities' as never) as Promise<ApiResult<CapabilityCatalogItem[]>>;
}

export function listExecutionActions() {
  return client.GET('/api/execution-actions' as never) as Promise<ApiResult<CapabilityCatalogItem[]>>;
}
