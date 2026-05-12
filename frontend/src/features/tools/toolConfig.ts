import type { components } from '../../types/api.generated';

export type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];
export type ToolConfigsByKey = Record<string, Record<string, unknown>>;

export type JsonSchemaField = {
  type?: string;
  enum?: unknown[];
  default?: unknown;
  description?: string;
};

export type ToolConfigField = {
  name: string;
  type: string;
  enumValues: unknown[];
  options: string[];
  label: string;
  help: string;
  widget: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function schemaProperties(tool: ToolCatalogResponse): Record<string, JsonSchemaField> {
  const schema = asRecord(tool.config_schema_json);
  const properties = asRecord(schema.properties);
  return Object.fromEntries(
    Object.entries(properties).filter(([, value]) => value !== null && typeof value === 'object' && !Array.isArray(value)),
  ) as Record<string, JsonSchemaField>;
}

function uiField(tool: ToolCatalogResponse, name: string): Record<string, unknown> {
  const uiSchema = asRecord(tool.ui_schema_json);
  const fields = asRecord(uiSchema.fields);
  return asRecord(fields[name]);
}

export function configurableFields(tool: ToolCatalogResponse): ToolConfigField[] {
  return Object.entries(schemaProperties(tool)).map(([name, field]) => {
    const ui = uiField(tool, name);
    const enumValues = Array.isArray(field.enum) ? field.enum : [];
    return {
      name,
      type: asString(field.type) || 'string',
      enumValues,
      options: enumValues.map((item) => String(item)),
      label: asString(ui.label) || name,
      help: asString(ui.help) || asString(field.description),
      widget: asString(ui.widget),
    };
  });
}

export function defaultToolConfig(tool: ToolCatalogResponse): Record<string, unknown> {
  const defaults = { ...asRecord(tool.default_config_json) };
  for (const [name, field] of Object.entries(schemaProperties(tool))) {
    if (defaults[name] === undefined && field.default !== undefined) {
      defaults[name] = field.default;
    }
  }
  return defaults;
}

export function initialConfigForTool(
  tool: ToolCatalogResponse,
  existingConfig: Record<string, unknown> | undefined,
): Record<string, unknown> {
  return { ...defaultToolConfig(tool), ...asRecord(existingConfig) };
}

export function mergeToolConfigValue(
  current: Record<string, unknown> | undefined,
  fieldName: string,
  value: unknown,
): Record<string, unknown> {
  const next = { ...asRecord(current) };
  if (value === undefined || value === '') {
    delete next[fieldName];
  } else {
    next[fieldName] = value;
  }
  return next;
}

export function toolByKey(tools: ToolCatalogResponse[]): Map<string, ToolCatalogResponse> {
  return new Map(tools.map((tool) => [tool.tool_key, tool]));
}
