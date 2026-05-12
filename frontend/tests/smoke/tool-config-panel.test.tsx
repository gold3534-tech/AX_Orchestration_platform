import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import type { components } from '../../src/types/api.generated';
import { ToolConfigPanel } from '../../src/features/tools/ToolConfigPanel';
import { defaultToolConfig } from '../../src/features/tools/toolConfig';

type ToolCatalogResponse = components['schemas']['ToolCatalogResponse'];

const nanoTool = {
  id: 'ax.nano_banana_image',
  tool_key: 'ax.nano_banana_image',
  name: 'AX Nano Banana Image',
  description: 'Generate image artifacts.',
  tool_type: 'python_class',
  module_path: 'api.tools.nano_banana_image_tool',
  class_name: 'AXNanoBananaImageTool',
  default_config_json: {
    model: 'gemini-3.1-flash-image-preview',
    aspect_ratio: '1:1',
    image_size: '1K',
  },
  config_schema_json: {
    type: 'object',
    properties: {
      model: {
        type: 'string',
        enum: ['gemini-2.5-flash-image', 'gemini-3-pro-image-preview', 'gemini-3.1-flash-image-preview'],
        default: 'gemini-3.1-flash-image-preview',
      },
      aspect_ratio: { type: 'string', enum: ['1:1', '9:16', '16:9'], default: '1:1' },
      image_size: { type: 'string', enum: ['1K', '2K', '4K'], default: '1K' },
    },
    additionalProperties: false,
  },
  input_schema_json: {},
  ui_schema_json: {
    fields: {
      model: { label: 'Model', widget: 'select' },
      aspect_ratio: { label: 'Output ratio', widget: 'select', help: 'Choose the generated image composition.' },
      image_size: { label: 'Image size', widget: 'select' },
    },
  },
  required_env_vars: [],
  credential_requirements: [],
  enabled: true,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: '2026-05-01T00:00:00Z',
} satisfies ToolCatalogResponse;

test('defaultToolConfig prefers catalog defaults and schema defaults', () => {
  const partialDefaultsTool = {
    ...nanoTool,
    default_config_json: {
      model: 'gemini-3.1-flash-image-preview',
    },
  } satisfies ToolCatalogResponse;

  expect(defaultToolConfig(partialDefaultsTool)).toEqual({
    model: 'gemini-3.1-flash-image-preview',
    aspect_ratio: '1:1',
    image_size: '1K',
  });
});

test('ToolConfigPanel renders selected Nano Banana config controls', () => {
  const handleChange = vi.fn();

  render(
    <ToolConfigPanel
      tools={[nanoTool]}
      selectedToolKeys={['ax.nano_banana_image']}
      toolConfigs={{
        'ax.nano_banana_image': { model: 'gemini-3.1-flash-image-preview', aspect_ratio: '1:1', image_size: '1K' },
      }}
      onChange={handleChange}
    />,
  );

  const panel = screen.getByRole('group', { name: /AX Nano Banana Image settings/i });
  fireEvent.change(within(panel).getByLabelText(/output ratio/i), { target: { value: '16:9' } });

  expect(handleChange).toHaveBeenCalledWith('ax.nano_banana_image', {
    model: 'gemini-3.1-flash-image-preview',
    aspect_ratio: '16:9',
    image_size: '1K',
  });
});

test('ToolConfigPanel updates Nano Banana model config while preserving image settings', () => {
  const handleChange = vi.fn();

  render(
    <ToolConfigPanel
      tools={[nanoTool]}
      selectedToolKeys={['ax.nano_banana_image']}
      toolConfigs={{
        'ax.nano_banana_image': { model: 'gemini-3.1-flash-image-preview', aspect_ratio: '9:16', image_size: '2K' },
      }}
      onChange={handleChange}
    />,
  );

  const panel = screen.getByRole('group', { name: /AX Nano Banana Image settings/i });
  const modelSelect = within(panel).getByLabelText('Model');
  expect(modelSelect).toHaveRole('combobox');

  fireEvent.change(modelSelect, { target: { value: 'gemini-2.5-flash-image' } });

  expect(handleChange).toHaveBeenCalledWith('ax.nano_banana_image', {
    model: 'gemini-2.5-flash-image',
    aspect_ratio: '9:16',
    image_size: '2K',
  });
});

test('ToolConfigPanel preserves numeric enum values when changing select controls', () => {
  const handleChange = vi.fn();
  const numericEnumTool = {
    ...nanoTool,
    id: 'ax.numeric_quality',
    tool_key: 'ax.numeric_quality',
    name: 'Numeric Quality',
    default_config_json: {
      quality: 1,
    },
    config_schema_json: {
      type: 'object',
      properties: {
        quality: { type: 'integer', enum: [1, 2, 3], default: 1 },
      },
      additionalProperties: false,
    },
    ui_schema_json: {
      fields: {
        quality: { label: 'Quality', widget: 'select' },
      },
    },
  } satisfies ToolCatalogResponse;

  render(
    <ToolConfigPanel
      tools={[numericEnumTool]}
      selectedToolKeys={['ax.numeric_quality']}
      toolConfigs={{ 'ax.numeric_quality': { quality: 1 } }}
      onChange={handleChange}
    />,
  );

  const panel = screen.getByRole('group', { name: /Numeric Quality settings/i });
  const qualitySelect = within(panel).getByLabelText(/quality/i);
  expect(qualitySelect).toHaveRole('combobox');

  fireEvent.change(qualitySelect, { target: { value: '2' } });

  expect(handleChange).toHaveBeenCalledWith('ax.numeric_quality', {
    quality: 2,
  });
});

test('ToolConfigPanel renders Instagram publish mode config as numeric options', () => {
  const handleChange = vi.fn();
  const instagramTool = {
    ...nanoTool,
    id: 'ax.instagram_publish_tool',
    tool_key: 'ax.instagram_publish_tool',
    name: 'AX Instagram Publish',
    description: 'Publish images to Instagram.',
    module_path: 'api.tools.instagram_publish_tool',
    class_name: 'AXInstagramPublishTool',
    default_config_json: {
      publish_mode: 3,
    },
    config_schema_json: {
      type: 'object',
      properties: {
        publish_mode: { type: 'integer', enum: [1, 3], default: 3 },
      },
      additionalProperties: false,
    },
    ui_schema_json: {
      fields: {
        publish_mode: {
          label: 'Publish preference',
          widget: 'select',
          help: 'The tool publishes 1 unique artifact as a single post and 3 unique artifacts as a carousel.',
          options: [1, 3],
        },
      },
    },
  } satisfies ToolCatalogResponse;

  render(
    <ToolConfigPanel
      tools={[instagramTool]}
      selectedToolKeys={['ax.instagram_publish_tool']}
      toolConfigs={{ 'ax.instagram_publish_tool': { publish_mode: 3 } }}
      onChange={handleChange}
    />,
  );

  const panel = screen.getByRole('group', { name: /AX Instagram Publish settings/i });
  const publishModeSelect = within(panel).getByLabelText(/publish preference/i);
  expect(publishModeSelect).toHaveValue('3');

  fireEvent.change(publishModeSelect, { target: { value: '1' } });

  expect(handleChange).toHaveBeenCalledWith('ax.instagram_publish_tool', {
    publish_mode: 1,
  });
});

test('ToolConfigPanel hides tools without configurable fields', () => {
  const handleChange = vi.fn();
  const bareTool = {
    ...nanoTool,
    id: 'crewai.file_read',
    tool_key: 'crewai.file_read',
    name: 'File Read',
    default_config_json: {},
    config_schema_json: {},
    ui_schema_json: {},
  } satisfies ToolCatalogResponse;

  const { container } = render(
    <ToolConfigPanel
      tools={[bareTool]}
      selectedToolKeys={['crewai.file_read']}
      toolConfigs={{}}
      onChange={handleChange}
    />,
  );

  expect(container).toBeEmptyDOMElement();
});
