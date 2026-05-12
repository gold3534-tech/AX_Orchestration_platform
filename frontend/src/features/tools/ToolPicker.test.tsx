import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import { ToolPicker } from './ToolPicker';

test('keeps the picker constrained inside narrow task columns', () => {
  render(
    <ToolPicker
      tools={['crewai.directory_read', 'crewai.file_read', 'crewai.csv_search']}
      selectedTools={[]}
      onChange={vi.fn()}
    />,
  );

  const fieldset = screen.getByRole('group', { name: 'Tools' });
  const select = screen.getByRole('combobox', { name: 'Tool to add' });
  const addButton = screen.getByRole('button', { name: 'Add tool' });

  expect(fieldset).toHaveClass('min-w-0', 'max-w-full', 'overflow-hidden');
  expect(select).toHaveClass('min-w-0', 'truncate');
  expect(addButton).toHaveClass('shrink-0');
});
