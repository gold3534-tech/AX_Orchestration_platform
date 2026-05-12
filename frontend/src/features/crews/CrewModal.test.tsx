import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { CrewModal } from './CrewModal';
import { createCrewFormValues, DEFAULT_HIERARCHICAL_MANAGER_LLM } from './hooks';

function renderCrewModal(overrides: Partial<Parameters<typeof CrewModal>[0]> = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();

  render(
    <CrewModal
      open
      mode="create"
      resetKey="test-modal"
      initialValues={createCrewFormValues()}
      availableAgents={[]}
      onClose={onClose}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );

  return {
    onSubmit: overrides.onSubmit ?? onSubmit,
    onClose,
  };
}

test('selecting hierarchical fills the default manager llm', () => {
  renderCrewModal();

  fireEvent.click(screen.getByRole('button', { name: /hierarchical/i }));

  expect(screen.getByRole('textbox', { name: /manager llm/i })).toHaveValue(
    DEFAULT_HIERARCHICAL_MANAGER_LLM,
  );
});

test('submitting hierarchical with a blank manager llm uses the default manager llm', async () => {
  const onSubmit = vi.fn();
  renderCrewModal({ onSubmit });

  fireEvent.change(screen.getByRole('textbox', { name: /crew name/i }), {
    target: { value: 'Hierarchical crew' },
  });
  fireEvent.click(screen.getByRole('button', { name: /hierarchical/i }));
  fireEvent.change(screen.getByRole('textbox', { name: /manager llm/i }), {
    target: { value: '   ' },
  });
  fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        process: 'hierarchical',
        managerLlm: DEFAULT_HIERARCHICAL_MANAGER_LLM,
      }),
    );
  });
});
