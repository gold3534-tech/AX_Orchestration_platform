import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import {
  FieldGroup,
  MultiSelector,
  NumberInput,
  parseOptionalFiniteNumber,
  SchemaBuilder,
  Section,
  SelectInput,
  TextInput,
  Toggle,
} from '../../src/components/shared/ConfigUI';

test('shared config controls render and emit changes', () => {
  const handleToggle = vi.fn();
  const handleSchemaChange = vi.fn();

  render(
    <Section title="Runtime">
      <FieldGroup label="Tools">
        <MultiSelector
          options={['Search', 'Calculator']}
          selected={['Search']}
          onAdd={vi.fn()}
          onRemove={vi.fn()}
          placeholder="Select a tool..."
        />
      </FieldGroup>
      <Toggle label="Verbose Logging" value={false} onChange={handleToggle} />
      <SchemaBuilder fields={[]} onChange={handleSchemaChange} />
    </Section>,
  );

  fireEvent.click(screen.getByRole('switch', { name: /verbose logging/i }));
  fireEvent.click(screen.getByRole('button', { name: /add field/i }));

  expect(handleToggle).toHaveBeenCalledWith(true);
  expect(handleSchemaChange).toHaveBeenCalledWith([
    { name: '', type: 'str', description: '', required: true },
  ]);
});

test('shared config inputs are named by their field groups', () => {
  render(
    <div>
      <FieldGroup label="Role">
        <TextInput value="" onChange={vi.fn()} />
      </FieldGroup>
      <FieldGroup label="Max Iter">
        <NumberInput value={undefined} onChange={vi.fn()} />
      </FieldGroup>
      <FieldGroup label="LLM Config">
        <SelectInput options={['gpt-4o']} value="" onChange={vi.fn()} />
      </FieldGroup>
      <FieldGroup label="Agent Tools">
        <MultiSelector options={['Search']} selected={[]} onAdd={vi.fn()} onRemove={vi.fn()} />
      </FieldGroup>
    </div>,
  );

  expect(screen.getByLabelText('Role')).toBeInTheDocument();
  expect(screen.getByRole('spinbutton', { name: 'Max Iter' })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'LLM Config' })).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: 'Agent Tools' })).toBeInTheDocument();
});

test('number input parsing emits undefined for non-finite numeric values', () => {
  const overflowingNumber = '9'.repeat(400);

  expect(parseOptionalFiniteNumber(overflowingNumber)).toBeUndefined();
  expect(parseOptionalFiniteNumber('120')).toBe(120);
});
