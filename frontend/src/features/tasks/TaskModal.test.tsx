import { render, screen, within } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { TaskModal } from './TaskModal';
import type { TaskFormValues } from './hooks';

const initialValues: TaskFormValues = {
  name: 'Research task',
  description: 'Collect facts',
  expectedOutput: 'A concise report',
  outputType: 'Raw',
  outputSchemaFields: [],
  outputFile: '',
  inputPresets: [],
  tools: [],
  toolConfigs: {},
};

function renderTaskModal(overrides: Partial<Parameters<typeof TaskModal>[0]> = {}) {
  render(
    <TaskModal
      open
      mode="create"
      resetKey="test-modal"
      initialValues={initialValues}
      inputPresets={[]}
      availableTools={[]}
      availableToolCatalog={[]}
      taskOptions={[]}
      onClose={vi.fn()}
      onSubmit={vi.fn()}
      {...overrides}
    />,
  );
}

test('does not render knowledge attachment controls for tasks', () => {
  renderTaskModal();

  const dialog = within(screen.getByRole('dialog', { name: /configure task/i }));

  expect(dialog.queryByRole('combobox', { name: /knowledge/i })).not.toBeInTheDocument();
  expect(dialog.queryByRole('button', { name: /knowledge/i })).not.toBeInTheDocument();
  expect(dialog.queryByRole('textbox', { name: /knowledge/i })).not.toBeInTheDocument();
  expect(dialog.queryByLabelText(/knowledge/i)).not.toBeInTheDocument();
  expect(dialog.queryByPlaceholderText(/knowledge/i)).not.toBeInTheDocument();
  expect(dialog.queryByText(/knowledge (sources?|attachments?)/i)).not.toBeInTheDocument();
});
