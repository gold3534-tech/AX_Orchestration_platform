import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { ToolConfigPanel } from './ToolConfigPanel';
import type { ToolCatalogResponse } from './toolConfig';

const instagramTool = {
  id: 'tool-1',
  tool_key: 'ax.instagram_publish_tool',
  name: 'AX Instagram Publish',
  description: 'Publish AX image artifacts to Instagram.',
  module_path: 'api.tools.instagram_publish_tool',
  class_name: 'AXInstagramPublishTool',
  tool_type: 'python_class',
  default_config_json: {
    publish_mode: 3,
    poll_timeout_seconds: 60,
    poll_interval_seconds: 3,
  },
  config_schema_json: {
    type: 'object',
    properties: {
      publish_mode: {
        type: 'integer',
        enum: [1, 3],
        default: 3,
      },
      poll_timeout_seconds: {
        type: 'integer',
        minimum: 1,
        maximum: 300,
        default: 60,
        description: 'Maximum seconds to wait for Meta media processing before publishing.',
      },
      poll_interval_seconds: {
        type: 'integer',
        minimum: 1,
        maximum: 60,
        default: 3,
        description: 'Seconds between Meta container status checks.',
      },
    },
    additionalProperties: false,
  },
  input_schema_json: {},
  ui_schema_json: {
    fields: {
      publish_mode: {
        widget: 'select',
        label: 'Publish preference',
        help: 'The tool publishes 1 unique artifact as a single post and 3 unique artifacts as a carousel.',
        options: [1, 3],
      },
      poll_timeout_seconds: {
        widget: 'number',
        label: 'Publish wait timeout',
        help: 'Maximum seconds to wait for Meta media processing before publishing.',
      },
      poll_interval_seconds: {
        widget: 'number',
        label: 'Status check interval',
        help: 'Seconds between Meta container status checks.',
      },
    },
  },
  required_env_vars: [],
  credential_requirements: [],
  enabled: true,
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:00:00Z',
} satisfies ToolCatalogResponse;

test('renders and updates instagram polling settings from schema', () => {
  const onChange = vi.fn();

  render(
    <ToolConfigPanel
      tools={[instagramTool]}
      selectedToolKeys={['ax.instagram_publish_tool']}
      toolConfigs={{}}
      onChange={onChange}
    />,
  );

  expect(screen.getByRole('group', { name: 'AX Instagram Publish settings' })).toBeInTheDocument();
  expect(screen.getByRole('spinbutton', { name: 'Publish wait timeout' })).toHaveValue(60);
  expect(screen.getByRole('spinbutton', { name: 'Status check interval' })).toHaveValue(3);

  fireEvent.change(screen.getByRole('spinbutton', { name: 'Publish wait timeout' }), {
    target: { value: '90' },
  });

  expect(onChange).toHaveBeenCalledWith('ax.instagram_publish_tool', {
    publish_mode: 3,
    poll_timeout_seconds: 90,
    poll_interval_seconds: 3,
  });
});
