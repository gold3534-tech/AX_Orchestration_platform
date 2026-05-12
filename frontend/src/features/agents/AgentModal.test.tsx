import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { expect, test, vi } from 'vitest';

import { AgentModal } from './AgentModal';
import type { AgentAttachmentValues, AgentFormValues } from './hooks';
import type { LLMModelOption } from './llmCatalog';

const llmModels: LLMModelOption[] = [
  {
    value: 'openai/gpt-4.1',
    label: 'GPT-4.1 · OpenAI',
    providerKey: 'openai',
    providerLabel: 'OpenAI',
    metadata: {
      parameters: {
        temperature: { supported: true, min: 0, max: 2, default: 0.7 },
        max_tokens: { supported: true, min: 1, max: 32000, default: 4096 },
      },
    },
  },
  {
    value: 'openai/gpt-5',
    label: 'GPT-5 · OpenAI',
    providerKey: 'openai',
    providerLabel: 'OpenAI',
    metadata: {
      parameters: {
        temperature: { supported: false },
        max_tokens: { supported: true, min: 16, max: 128000, default: 8192 },
      },
    },
  },
  {
    value: 'anthropic/claude-sonnet',
    label: 'Claude Sonnet · Anthropic',
    providerKey: 'anthropic',
    providerLabel: 'Anthropic',
    metadata: {
      parameters: {
        temperature: { supported: true, min: 0, max: 1, default: 0.3 },
        max_tokens: { supported: true, min: 1, max: 64000, default: 2048 },
      },
    },
  },
  {
    value: 'openai/incomplete-temperature',
    label: 'Incomplete Temperature · OpenAI',
    providerKey: 'openai',
    providerLabel: 'OpenAI',
    metadata: {
      parameters: {
        temperature: { supported: true },
        max_tokens: { supported: true, min: 1, max: 4096, default: 1024 },
      },
    },
  },
];

const initialValues: AgentFormValues = {
  role: 'Researcher',
  goal: 'Find signals',
  backstory: 'Careful analyst',
};

function renderAgentModal(overrides: Partial<ComponentProps<typeof AgentModal>> = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();

  render(
    <AgentModal
      open
      mode="create"
      resetKey="test-modal"
      initialValues={initialValues}
      availableTools={[]}
      availableKnowledgeSources={[]}
      initialAttachments={{ tools: [], knowledgeSources: [] }}
      llmModels={llmModels}
      embedders={[]}
      onClose={onClose}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Model Configuration' }));

  return {
    dialog: within(screen.getByRole('dialog', { name: /configure agent/i })),
    onSubmit: overrides.onSubmit ?? onSubmit,
    onClose,
  };
}

function changeModel(label: string, value: string) {
  fireEvent.change(screen.getByRole('combobox', { name: label }), { target: { value } });
}

function save() {
  fireEvent.click(screen.getByRole('button', { name: /save configuration/i }));
}

test('selecting a model that supports temperature and max tokens shows both controls', () => {
  renderAgentModal();

  changeModel('LLM', 'GPT-4.1 · OpenAI');

  expect(screen.getByRole('slider', { name: 'Temperature' })).toHaveValue('0.7');
  expect(screen.getByRole('spinbutton', { name: 'Max tokens' })).toHaveValue(4096);
});

test('selecting a GPT-5-like model hides temperature and shows max tokens', () => {
  renderAgentModal();

  changeModel('LLM', 'GPT-5 · OpenAI');

  expect(screen.queryByRole('slider', { name: 'Temperature' })).not.toBeInTheDocument();
  expect(screen.getByRole('spinbutton', { name: 'Max tokens' })).toHaveValue(8192);
});

test('submitting selected primary LLM includes model provider and max token default', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({ onSubmit });

  changeModel('LLM', 'GPT-4.1 · OpenAI');
  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        llm: 'openai/gpt-4.1',
        llmProvider: 'openai',
        llmTemperature: 0.7,
        llmMaxTokens: 4096,
      }),
      expect.objectContaining<AgentAttachmentValues>({
        tools: [],
        knowledgeSources: [],
      }),
    );
  });
});

test('submitting a model with unsupported temperature omits stale initial temperature', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({
    initialValues: {
      ...initialValues,
      llm: 'openai/gpt-5',
      llmProvider: 'openai',
      llmTemperature: 0.7,
      llmMaxTokens: 8192,
    },
    onSubmit,
  });

  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        llm: 'openai/gpt-5',
        llmProvider: 'openai',
        llmMaxTokens: 8192,
      }),
      expect.anything(),
    );
  });
  const [submittedValues] = onSubmit.mock.calls[0] as [AgentFormValues, AgentAttachmentValues];

  expect(submittedValues).not.toHaveProperty('llmTemperature');
});

test('submitting an unknown catalog model omits stale primary parameters', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({
    initialValues: {
      ...initialValues,
      llm: 'openai/unknown',
      llmProvider: 'openai',
      llmTemperature: 0.7,
      llmMaxTokens: 4096,
    },
    onSubmit,
  });

  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        llm: 'openai/unknown',
        llmProvider: 'openai',
      }),
      expect.anything(),
    );
  });
  const [submittedValues] = onSubmit.mock.calls[0] as [AgentFormValues, AgentAttachmentValues];

  expect(submittedValues).not.toHaveProperty('llmTemperature');
  expect(submittedValues).not.toHaveProperty('llmMaxTokens');
});

test('incomplete temperature metadata hides control and omits stale temperature', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({
    initialValues: {
      ...initialValues,
      llm: 'openai/incomplete-temperature',
      llmProvider: 'openai',
      llmTemperature: 0.7,
      llmMaxTokens: 1024,
    },
    onSubmit,
  });

  expect(screen.queryByRole('slider', { name: 'Temperature' })).not.toBeInTheDocument();

  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        llm: 'openai/incomplete-temperature',
        llmProvider: 'openai',
        llmMaxTokens: 1024,
      }),
      expect.anything(),
    );
  });
  const [submittedValues] = onSubmit.mock.calls[0] as [AgentFormValues, AgentAttachmentValues];

  expect(submittedValues).not.toHaveProperty('llmTemperature');
});

test('function calling LLM selection sets provider without primary parameter leakage', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({ onSubmit });

  changeModel('Function Calling LLM', 'Claude Sonnet · Anthropic');
  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        function_calling_llm: 'anthropic/claude-sonnet',
        functionCallingLlmProvider: 'anthropic',
      }),
      expect.anything(),
    );
  });
  const [submittedValues] = onSubmit.mock.calls[0] as [AgentFormValues, AgentAttachmentValues];

  expect(submittedValues).not.toHaveProperty('llmTemperature');
  expect(submittedValues).not.toHaveProperty('llmMaxTokens');
});

test('invalid max tokens value blocks submit', () => {
  const onSubmit = vi.fn();
  renderAgentModal({ onSubmit });

  changeModel('LLM', 'GPT-4.1 · OpenAI');
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Max tokens' }), { target: { value: '4096.5' } });
  save();

  expect(screen.getByText(/max tokens must be a whole number/i)).toBeInTheDocument();
  expect(onSubmit).not.toHaveBeenCalled();
});

test('renders ready knowledge sources as attachable Agent knowledge', () => {
  renderAgentModal({
    availableKnowledgeSources: [
      { id: 'k1', name: 'Product FAQ', status: 'ready', source_file_name: 'faq.txt' },
    ],
    initialAttachments: { tools: [], toolConfigs: {}, knowledgeSources: ['k1'] },
  });

  expect(screen.getByText('Product FAQ')).toBeInTheDocument();
});

test('only offers ready knowledge sources for attachment', () => {
  renderAgentModal({
    availableKnowledgeSources: [
      { id: 'ready-1', name: 'Ready FAQ', status: 'ready', source_file_name: 'ready.pdf' },
      { id: 'failed-1', name: 'Failed FAQ', status: 'failed', source_file_name: 'failed.pdf' },
    ],
    initialAttachments: { tools: [], toolConfigs: {}, knowledgeSources: [] },
  });

  expect(screen.getByText('Ready FAQ')).toBeInTheDocument();
  expect(screen.queryByText('Failed FAQ')).not.toBeInTheDocument();
});

test('submitting duplicate knowledge names preserves selected knowledge IDs', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({
    availableKnowledgeSources: [
      { id: 'k1', name: 'Product FAQ', status: 'ready', source_file_name: 'faq-a.txt' },
      { id: 'k2', name: 'Product FAQ', status: 'ready', source_file_name: 'faq-b.txt' },
    ],
    initialAttachments: { tools: [], toolConfigs: {}, knowledgeSources: ['k1'] },
    onSubmit,
  });

  expect(screen.getByText('Product FAQ · faq-a.txt · k1')).toBeInTheDocument();
  expect(screen.getByText('Product FAQ · faq-b.txt · k2')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Remove Product FAQ · faq-a.txt · k1' })).toBeInTheDocument();

  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining<AgentAttachmentValues>({
        tools: [],
        knowledgeSources: ['k1'],
      }),
    );
  });
});

test('disambiguates duplicate knowledge names with duplicate source file names', async () => {
  const onSubmit = vi.fn();
  renderAgentModal({
    availableKnowledgeSources: [
      { id: 'alpha-1234', name: 'Product FAQ', status: 'ready', source_file_name: 'faq.txt' },
      { id: 'beta-5678', name: 'Product FAQ', status: 'ready', source_file_name: 'faq.txt' },
    ],
    initialAttachments: { tools: [], toolConfigs: {}, knowledgeSources: ['alpha-1234'] },
    onSubmit,
  });

  expect(screen.getByText('Product FAQ · faq.txt · alpha-12')).toBeInTheDocument();
  expect(screen.getByText('Product FAQ · faq.txt · beta-567')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Remove Product FAQ · faq.txt · alpha-12' })).toBeInTheDocument();

  save();

  await waitFor(() => {
    expect(onSubmit).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining<AgentAttachmentValues>({
        tools: [],
        knowledgeSources: ['alpha-1234'],
      }),
    );
  });
});
