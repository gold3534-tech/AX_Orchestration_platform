import { fireEvent, render, screen } from '@testing-library/react';
import { CrudModal } from '../../src/components/shared/CrudModal';
import { DeleteConfirm } from '../../src/components/shared/DeleteConfirm';

test('CrudModal focuses on open, closes on Escape, and restores focus on close', () => {
  const trigger = document.createElement('button');
  trigger.textContent = 'Open modal';
  document.body.appendChild(trigger);
  trigger.focus();

  const onClose = vi.fn();
  const { rerender, unmount } = render(
    <CrudModal open title="New agent" onClose={onClose}>
      <p>Body</p>
    </CrudModal>,
  );

  const dialog = screen.getByRole('dialog', { name: /new agent/i });
  expect(dialog).toHaveFocus();

  fireEvent.keyDown(dialog, { key: 'Escape' });
  expect(onClose).toHaveBeenCalledTimes(1);

  rerender(
    <CrudModal open={false} title="New agent" onClose={onClose}>
      <p>Body</p>
    </CrudModal>,
  );

  expect(trigger).toHaveFocus();

  unmount();
  trigger.remove();
});

test('CrudModal keeps Tab focus inside the open dialog', () => {
  render(
    <CrudModal open title="Edit agent" onClose={vi.fn()}>
      <button type="button">First action</button>
      <button type="button">Last action</button>
    </CrudModal>,
  );

  const dialog = screen.getByRole('dialog', { name: /edit agent/i });
  const closeButton = screen.getByRole('button', { name: /close/i });
  const lastButton = screen.getByRole('button', { name: /last action/i });

  lastButton.focus();
  fireEvent.keyDown(dialog, { key: 'Tab' });
  expect(closeButton).toHaveFocus();

  closeButton.focus();
  fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
  expect(lastButton).toHaveFocus();
});

test('DeleteConfirm exposes an accessible dialog description', () => {
  render(
    <DeleteConfirm
      open
      title="Delete agent"
      message="This action permanently removes the agent."
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );

  expect(screen.getByRole('dialog', { name: /delete agent/i })).toHaveAccessibleDescription(
    'This action permanently removes the agent.',
  );
});

test('CrudModal uses a readable light-mode surface', () => {
  render(
    <CrudModal open title="Edit agent" onClose={vi.fn()}>
      <p>Body</p>
    </CrudModal>,
  );

  const dialog = screen.getByRole('dialog', { name: /edit agent/i });
  expect(dialog).toHaveClass('border-stone-200', 'bg-white');
  expect(screen.getByRole('heading', { name: /edit agent/i })).toHaveClass('text-stone-950');
  expect(screen.getByRole('button', { name: /close/i })).toHaveClass('text-stone-700');
});

test('DeleteConfirm keeps helper copy and actions readable on light surfaces', () => {
  render(
    <DeleteConfirm
      open
      title="Delete crew"
      message="Delete the current crew draft?"
      onCancel={vi.fn()}
      onConfirm={vi.fn()}
    />,
  );

  expect(screen.getByText(/delete the current crew draft/i)).toHaveClass('text-stone-700');
  expect(screen.getByRole('button', { name: /cancel/i })).toHaveClass('text-stone-700');
  expect(screen.getByRole('button', { name: /confirm delete/i })).toHaveClass('text-rose-700');
});
