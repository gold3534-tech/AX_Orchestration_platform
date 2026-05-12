import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { ActionButton } from '../../src/components/shared/ActionButton';
import { ActionFeedbackDialog } from '../../src/components/shared/ActionFeedbackDialog';

test('action button shows spinner label and disables while pending', () => {
  render(
    <ActionButton isPending pendingLabel="Publishing...">
      Publish
    </ActionButton>,
  );

  expect(screen.getByRole('button', { name: /publishing/i })).toBeDisabled();
  expect(screen.getByTestId('action-button-spinner')).toBeInTheDocument();
});

test('action feedback dialog calls confirm cancel and retry actions', () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const onRetry = vi.fn();

  const { rerender } = render(
    <ActionFeedbackDialog
      open
      tone="confirm"
      title="현재 Flow를 새 버전으로 배포하시겠습니까?"
      confirmLabel="확인"
      cancelLabel="취소"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: '확인' }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: '취소' }));
  expect(onCancel).toHaveBeenCalledTimes(1);

  rerender(
    <ActionFeedbackDialog
      open
      tone="danger"
      title="배포에 실패했습니다. 다시 시도하시겠습니까?"
      confirmLabel="다시 시도"
      cancelLabel="취소"
      onConfirm={onRetry}
      onCancel={onCancel}
    />,
  );

  fireEvent.click(screen.getByRole('button', { name: '다시 시도' }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

test('action feedback dialog manages focus and Escape close behavior', () => {
  const onCancel = vi.fn();

  render(<button type="button">Before dialog</button>);
  const trigger = screen.getByRole('button', { name: 'Before dialog' });
  trigger.focus();

  const { rerender } = render(
    <ActionFeedbackDialog
      open
      title="배포 전 확인"
      description="현재 설정으로 Flow를 배포합니다."
      confirmLabel="확인"
      cancelLabel="취소"
      onCancel={onCancel}
    />,
  );

  const dialog = screen.getByRole('dialog', { name: '배포 전 확인' });
  expect(dialog).toHaveFocus();
  expect(dialog).toHaveAccessibleDescription('현재 설정으로 Flow를 배포합니다.');

  fireEvent.keyDown(dialog, { key: 'Escape' });
  expect(onCancel).toHaveBeenCalledTimes(1);

  rerender(
    <ActionFeedbackDialog
      open={false}
      title="배포 전 확인"
      description="현재 설정으로 Flow를 배포합니다."
      confirmLabel="확인"
      cancelLabel="취소"
      onCancel={onCancel}
    />,
  );

  expect(trigger).toHaveFocus();
});

test('action feedback dialog traps Tab focus within actions', () => {
  render(
    <>
      <button type="button">Outside before</button>
      <ActionFeedbackDialog
        open
        title="배포 전 확인"
        confirmLabel="확인"
        cancelLabel="취소"
        onCancel={vi.fn()}
      />
      <button type="button">Outside after</button>
    </>,
  );

  const cancelButton = screen.getByRole('button', { name: '취소' });
  const confirmButton = screen.getByRole('button', { name: '확인' });

  confirmButton.focus();
  fireEvent.keyDown(confirmButton, { key: 'Tab' });
  expect(cancelButton).toHaveFocus();

  expect(screen.getByRole('button', { name: 'Outside after' })).not.toHaveFocus();
});

test('action feedback dialog traps Shift Tab focus within actions', () => {
  render(
    <>
      <button type="button">Outside before</button>
      <ActionFeedbackDialog
        open
        title="배포 전 확인"
        confirmLabel="확인"
        cancelLabel="취소"
        onCancel={vi.fn()}
      />
      <button type="button">Outside after</button>
    </>,
  );

  const cancelButton = screen.getByRole('button', { name: '취소' });
  const confirmButton = screen.getByRole('button', { name: '확인' });

  cancelButton.focus();
  fireEvent.keyDown(cancelButton, { key: 'Tab', shiftKey: true });
  expect(confirmButton).toHaveFocus();

  expect(screen.getByRole('button', { name: 'Outside before' })).not.toHaveFocus();
});

test('action feedback dialog contains Shift Tab from initial dialog focus', () => {
  render(
    <>
      <button type="button">Outside before</button>
      <ActionFeedbackDialog
        open
        title="배포 전 확인"
        confirmLabel="확인"
        cancelLabel="취소"
        onCancel={vi.fn()}
      />
      <button type="button">Outside after</button>
    </>,
  );

  const dialog = screen.getByRole('dialog', { name: '배포 전 확인' });
  const confirmButton = screen.getByRole('button', { name: '확인' });

  expect(dialog).toHaveFocus();
  fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true });
  expect(confirmButton).toHaveFocus();

  expect(screen.getByRole('button', { name: 'Outside before' })).not.toHaveFocus();
});
