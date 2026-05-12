import { FieldGroup, NumberInput, SelectInput, TextInput, Toggle } from '../../components/shared/ConfigUI';
import {
  configurableFields,
  initialConfigForTool,
  mergeToolConfigValue,
  toolByKey,
  type ToolCatalogResponse,
  type ToolConfigField,
  type ToolConfigsByKey,
} from './toolConfig';

type ToolConfigPanelProps = {
  tools: ToolCatalogResponse[];
  selectedToolKeys: string[];
  toolConfigs: ToolConfigsByKey;
  onChange: (toolKey: string, config: Record<string, unknown>) => void;
};

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function asBoolean(value: unknown): boolean {
  return value === true;
}

function enumOptionForValue(field: ToolConfigField, value: unknown): string {
  const index = field.enumValues.findIndex((item) => Object.is(item, value));
  return index >= 0 ? field.options[index] : asString(value);
}

function enumValueForOption(field: ToolConfigField, option: string): unknown {
  const index = field.options.indexOf(option);
  return index >= 0 ? field.enumValues[index] : option;
}

function ConfigField({
  field,
  value,
  onChange,
}: {
  field: ToolConfigField;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  if (field.options.length > 0) {
    return (
      <SelectInput
        label={field.label}
        options={field.options}
        value={enumOptionForValue(field, value)}
        onChange={(option) => onChange(enumValueForOption(field, option))}
        placeholder="Select"
      />
    );
  }

  if (field.type === 'boolean') {
    return <Toggle label={field.label} description={field.help} value={asBoolean(value)} onChange={onChange} />;
  }

  if (field.type === 'integer' || field.type === 'number') {
    return (
      <FieldGroup label={field.label} helperText={field.help || undefined}>
        <NumberInput value={asNumber(value)} onChange={onChange} placeholder="Default" />
      </FieldGroup>
    );
  }

  return (
    <FieldGroup label={field.label} helperText={field.help || undefined}>
      <TextInput value={asString(value)} onChange={onChange} placeholder="Default" />
    </FieldGroup>
  );
}

export function ToolConfigPanel({ tools, selectedToolKeys, toolConfigs, onChange }: ToolConfigPanelProps) {
  const catalogByKey = toolByKey(tools);
  const panels = selectedToolKeys
    .map((toolKey) => {
      const tool = catalogByKey.get(toolKey);
      if (!tool) return null;
      const fields = configurableFields(tool);
      if (fields.length === 0) return null;
      const config = initialConfigForTool(tool, toolConfigs[toolKey]);
      return { tool, fields, config };
    })
    .filter(
      (panel): panel is { tool: ToolCatalogResponse; fields: ToolConfigField[]; config: Record<string, unknown> } =>
        Boolean(panel),
    );

  if (panels.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {panels.map(({ tool, fields, config }) => (
        <fieldset
          key={tool.tool_key}
          aria-label={`${tool.name} settings`}
          className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-3"
        >
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-stone-600">
            {tool.name} settings
          </legend>
          <div className="mt-3 space-y-3">
            {fields.map((field) => (
              <ConfigField
                key={field.name}
                field={field}
                value={config[field.name]}
                onChange={(value) => {
                  onChange(tool.tool_key, mergeToolConfigValue(config, field.name, value));
                }}
              />
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
