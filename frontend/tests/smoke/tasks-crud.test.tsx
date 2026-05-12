import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { expect, test, vi } from 'vitest';
import { TasksPage } from '../../src/features/tasks/TasksPage';

const taskHookMocks = vi.hoisted(() => ({
  STRUCTURED_EXPECTED_OUTPUT_PLACEHOLDER: "A JSON object with 'title' and 'content' fields.",
  structuredExpectedOutputFromFields: (fields: { name: string }[] = []) => {
    const names = fields.map((field) => field.name.trim()).filter(Boolean);

    if (names.length === 0) {
      return "A JSON object with 'title' and 'content' fields.";
    }

    if (names.length === 1) {
      return `A JSON object with '${names[0]}' fields.`;
    }

    const quotedNames = names.map((name) => `'${name}'`);
    const fieldList = names.length === 2
      ? `${quotedNames[0]} and ${quotedNames[1]}`
      : `${quotedNames.slice(0, -1).join(', ')}, and ${quotedNames[quotedNames.length - 1]}`;

    return `A JSON object with ${fieldList} fields.`;
  },
  useTasksLibrary: vi.fn(),
  useCreateTask: vi.fn(),
  useUpdateTask: vi.fn(),
  useDeleteTask: vi.fn(),
}));

vi.mock('../../src/features/tasks/hooks', () => taskHookMocks);

function arrangeTasksPage({ createPending = false }: { createPending?: boolean } = {}) {
  const createMutate = vi.fn(async () => undefined);
  const updateMutate = vi.fn(async () => undefined);
  const deleteMutate = vi.fn(async () => undefined);

  taskHookMocks.useTasksLibrary.mockReturnValue({
    tasks: [
      {
        assetId: 'task-1',
        versionId: 'task-v1',
        name: 'SEO Brief',
        description: 'Collect the main search intent signals.',
        expectedOutput: 'A concise SEO brief.',
        outputType: 'Raw',
        outputSchemaFields: [],
        inputPresets: ['website_url', 'keyword'],
        tools: ['crewai.web_search'],
        summary: 'Collect the main search intent signals.',
        status: 'Draft',
      },
    ],
    inputPresets: [
      { key: 'website_url', label: '웹 사이트', inputType: 'url', description: '분석할 웹사이트 주소' },
      { key: 'keyword', label: '검색어', inputType: 'text', description: '핵심 검색어' },
      { key: 'brand_name', label: '브랜드명', inputType: 'text', description: '브랜드 이름' },
      { key: 'target_audience', label: '타겟 독자', inputType: 'text', description: '핵심 독자층' },
    ],
    tools: ['crewai.web_search', 'crewai.file_read'],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    presetCatalogError: null,
    isPresetCatalogLoading: false,
    refetchPresetCatalog: vi.fn(),
  });
  taskHookMocks.useCreateTask.mockReturnValue({ mutateAsync: createMutate, isPending: createPending });
  taskHookMocks.useUpdateTask.mockReturnValue({ mutateAsync: updateMutate, isPending: false });
  taskHookMocks.useDeleteTask.mockReturnValue({ mutateAsync: deleteMutate, isPending: false });

  renderTasksPage();

  return { createMutate, updateMutate, deleteMutate };
}

function renderTasksPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/build/tasks']}>
        <TasksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function addPreset(modal: ReturnType<typeof within>, key: string) {
  fireEvent.change(modal.getByLabelText(/input presets/i), {
    target: { value: key },
  });
}

function addTool(modal: ReturnType<typeof within>, key: string) {
  fireEvent.change(modal.getByLabelText(/tool to add/i), {
    target: { value: key },
  });
  fireEvent.click(modal.getByRole('button', { name: /add tool/i }));
}

function removePreset(modal: ReturnType<typeof within>, index: number) {
  fireEvent.click(modal.getAllByRole('button', { name: /^remove$/i })[index]);
}

function selectTaskFromLibrary() {
  fireEvent.click(screen.getByRole('button', { name: /SEO Brief/i }));
}

test('opens the configure task modal from the tasks library', async () => {
  arrangeTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));

  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  expect(within(dialog).getByRole('textbox', { name: /Name/i })).toBeInTheDocument();
  expect(within(dialog).getByLabelText(/input presets/i)).toBeInTheDocument();
  expect(screen.queryByText('Representative')).not.toBeInTheDocument();
  expect(screen.queryByText('CrewAI Trigger Context')).not.toBeInTheDocument();
});

test('task modal supports structured output and inspector stays read-only', async () => {
  arrangeTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const createDialog = screen.getByRole('dialog', { name: /configure task/i });
  const createModal = within(createDialog);

  fireEvent.change(createModal.getByLabelText(/output type/i), { target: { value: 'Output JSON' } });

  expect(createModal.getByRole('textbox', { name: /expected output/i })).toHaveAttribute(
    'placeholder',
    "A JSON object with 'title' and 'content' fields.",
  );
  expect(createModal.getByRole('button', { name: /add field/i })).toBeInTheDocument();

  fireEvent.click(createModal.getByRole('button', { name: /cancel/i }));
  selectTaskFromLibrary();

  const inspector = screen.getByText(/selected task details/i).closest('section');
  expect(inspector).not.toBeNull();
  const panel = within(inspector!);

  expect(panel.queryByRole('textbox', { name: /expected output/i })).not.toBeInTheDocument();
  expect(panel.getByText(/A concise SEO brief./i)).toBeInTheDocument();

  fireEvent.click(panel.getByRole('button', { name: /edit/i }));

  expect(screen.getByRole('dialog', { name: /configure task/i })).toBeInTheDocument();
});

test('structured output requires at least one identifier-safe schema field', async () => {
  arrangeTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  const modal = within(dialog);

  fireEvent.change(modal.getByLabelText(/^Name$/i), { target: { value: 'Structured Brief' } });
  fireEvent.change(modal.getByLabelText(/description/i), { target: { value: 'Return a structured brief.' } });
  fireEvent.change(modal.getByLabelText(/output type/i), { target: { value: 'Output JSON' } });

  expect(modal.getByRole('button', { name: /create task/i })).toBeDisabled();

  fireEvent.click(modal.getByRole('button', { name: /add field/i }));
  fireEvent.change(modal.getByLabelText(/field 1 name/i), { target: { value: 'bad name' } });

  expect(modal.getByRole('button', { name: /create task/i })).toBeDisabled();

  fireEvent.change(modal.getByLabelText(/field 1 name/i), { target: { value: 'summary' } });

  expect(modal.getByRole('button', { name: /create task/i })).toBeEnabled();
});

test('structured task creation defaults expected output when the text field is empty', async () => {
  const { createMutate } = arrangeTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  const modal = within(dialog);

  fireEvent.change(modal.getByLabelText(/^Name$/i), { target: { value: 'Structured Brief' } });
  fireEvent.change(modal.getByLabelText(/description/i), { target: { value: 'Return a structured brief.' } });
  fireEvent.change(modal.getByLabelText(/output type/i), { target: { value: 'Output JSON' } });
  fireEvent.click(modal.getByRole('button', { name: /add field/i }));
  fireEvent.change(modal.getByLabelText(/field 1 name/i), { target: { value: 'title' } });
  fireEvent.click(modal.getByRole('button', { name: /add field/i }));
  fireEvent.change(modal.getByLabelText(/field 2 name/i), { target: { value: 'content' } });
  fireEvent.click(modal.getByRole('button', { name: /create task/i }));

  await waitFor(() => {
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        expectedOutput: "A JSON object with 'title' and 'content' fields.",
        outputType: 'Output JSON',
        outputSchemaFields: [
          { name: 'title', type: 'str', description: '', required: true },
          { name: 'content', type: 'str', description: '', required: true },
        ],
      }),
    );
  });
});

test('escape does not close the task modal while submitting', async () => {
  arrangeTasksPage({ createPending: true });

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });

  fireEvent.keyDown(dialog, { key: 'Escape' });

  expect(screen.getByRole('dialog', { name: /configure task/i })).toBeInTheDocument();
});

test('switches to list view and shows task rows with preset presence', async () => {
  arrangeTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /List/i }));

  expect(screen.getByRole('columnheader', { name: /description/i })).toBeInTheDocument();
  expect(screen.getByRole('row', { name: /SEO Brief Collect the main search intent signals./i })).toBeInTheDocument();
});

test('creates a task with name, description, expected output, preset keys, and tools', async () => {
  const { createMutate } = arrangeTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  const modal = within(dialog);

  fireEvent.change(modal.getByLabelText(/^Name$/i), { target: { value: 'Competitive Brief' } });
  fireEvent.change(modal.getByLabelText(/description/i), { target: { value: 'Compare top ranking pages.' } });
  fireEvent.change(modal.getByLabelText(/expected output/i), { target: { value: 'A competitor summary document.' } });
  addPreset(modal, 'brand_name');
  addTool(modal, 'crewai.web_search');
  addTool(modal, 'crewai.file_read');
  fireEvent.click(modal.getByRole('button', { name: /create task/i }));

  await waitFor(() => {
    expect(createMutate).toHaveBeenCalledWith({
      name: 'Competitive Brief',
      description: 'Compare top ranking pages. {brand_name}',
      expectedOutput: 'A competitor summary document.',
      outputType: 'Raw',
      outputSchemaFields: [],
      asyncExecution: undefined,
      humanInput: undefined,
      markdown: undefined,
      guardrailMaxRetries: undefined,
      outputFile: '',
      createDirectory: undefined,
      inputPresets: ['brand_name'],
      tools: ['crewai.web_search', 'crewai.file_read'],
      toolConfigs: {
        'crewai.web_search': {},
        'crewai.file_read': {},
      },
    });
  });
});

test('task modal submits Nano Banana tool config', async () => {
  const createMutate = vi.fn(async () => undefined);
  taskHookMocks.useTasksLibrary.mockReturnValue({
    tasks: [],
    inputPresets: [],
    tools: ['ax.nano_banana_image'],
    toolCatalog: [
      {
        id: 'ax.nano_banana_image',
        tool_key: 'ax.nano_banana_image',
        name: 'AX Nano Banana Image',
        description: 'Generate image artifacts.',
        tool_type: 'python_class',
        module_path: 'api.tools.nano_banana_image_tool',
        class_name: 'AXNanoBananaImageTool',
        default_config_json: { model: 'gemini-3.1-flash-image-preview', aspect_ratio: '1:1', image_size: '1K' },
        config_schema_json: {
          type: 'object',
          properties: {
            model: { type: 'string', enum: ['gemini-3.1-flash-image-preview', 'gemini-3-pro-image-preview'] },
            aspect_ratio: { type: 'string', enum: ['1:1', '9:16', '16:9'] },
            image_size: { type: 'string', enum: ['1K', '2K', '4K'] },
          },
          additionalProperties: false,
        },
        input_schema_json: {},
        ui_schema_json: {
          fields: {
            model: { label: 'Model', widget: 'select' },
            aspect_ratio: { label: 'Output ratio', widget: 'select' },
            image_size: { label: 'Image size', widget: 'select' },
          },
        },
        required_env_vars: [],
        credential_requirements: [],
        enabled: true,
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    presetCatalogError: null,
    isPresetCatalogLoading: false,
    refetchPresetCatalog: vi.fn(),
  });
  taskHookMocks.useCreateTask.mockReturnValue({ mutateAsync: createMutate, isPending: false });
  taskHookMocks.useUpdateTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  taskHookMocks.useDeleteTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  renderTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /\+ new/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  const modal = within(dialog);
  fireEvent.change(modal.getByLabelText(/name/i), { target: { value: 'Generate product image' } });
  fireEvent.change(modal.getByLabelText(/description/i), { target: { value: 'Create an image.' } });
  fireEvent.change(modal.getByLabelText(/expected output/i), { target: { value: 'One image artifact.' } });
  fireEvent.change(modal.getByLabelText(/tool to add/i), { target: { value: 'ax.nano_banana_image' } });
  fireEvent.click(modal.getByRole('button', { name: /add tool/i }));
  fireEvent.change(modal.getByLabelText(/output ratio/i), { target: { value: '9:16' } });
  fireEvent.click(modal.getByRole('button', { name: /create task/i }));

  await waitFor(() => {
    expect(createMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Generate product image',
        tools: ['ax.nano_banana_image'],
        toolConfigs: {
          'ax.nano_banana_image': {
            model: 'gemini-3.1-flash-image-preview',
            aspect_ratio: '9:16',
            image_size: '1K',
          },
        },
      }),
    );
  });
});

test('task modal seeds defaults when editing a configured tool with empty config', async () => {
  const updateMutate = vi.fn(async () => undefined);
  taskHookMocks.useTasksLibrary.mockReturnValue({
    tasks: [
      {
        assetId: 'task-image',
        versionId: 'task-image-v1',
        name: 'Generate Image',
        description: 'Create an image.',
        expectedOutput: 'One image artifact.',
        outputType: 'Raw',
        outputSchemaFields: [],
        inputPresets: [],
        tools: ['ax.nano_banana_image'],
        toolConfigs: {},
        summary: 'Create an image.',
        status: 'Draft',
      },
    ],
    inputPresets: [],
    tools: ['ax.nano_banana_image'],
    toolCatalog: [
      {
        id: 'ax.nano_banana_image',
        tool_key: 'ax.nano_banana_image',
        name: 'AX Nano Banana Image',
        description: 'Generate image artifacts.',
        tool_type: 'python_class',
        module_path: 'api.tools.nano_banana_image_tool',
        class_name: 'AXNanoBananaImageTool',
        default_config_json: { model: 'gemini-3.1-flash-image-preview', aspect_ratio: '1:1', image_size: '1K' },
        config_schema_json: {
          type: 'object',
          properties: {
            model: { type: 'string', enum: ['gemini-3.1-flash-image-preview', 'gemini-3-pro-image-preview'] },
            aspect_ratio: { type: 'string', enum: ['1:1', '9:16', '16:9'] },
            image_size: { type: 'string', enum: ['1K', '2K', '4K'] },
          },
          additionalProperties: false,
        },
        input_schema_json: {},
        ui_schema_json: {
          fields: {
            model: { label: 'Model', widget: 'select' },
            aspect_ratio: { label: 'Output ratio', widget: 'select' },
            image_size: { label: 'Image size', widget: 'select' },
          },
        },
        required_env_vars: [],
        credential_requirements: [],
        enabled: true,
        created_at: '2026-05-01T00:00:00Z',
        updated_at: '2026-05-01T00:00:00Z',
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    presetCatalogError: null,
    isPresetCatalogLoading: false,
    refetchPresetCatalog: vi.fn(),
  });
  taskHookMocks.useCreateTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  taskHookMocks.useUpdateTask.mockReturnValue({ mutateAsync: updateMutate, isPending: false });
  taskHookMocks.useDeleteTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  renderTasksPage();

  fireEvent.click(screen.getByRole('button', { name: /Generate Image/i }));
  fireEvent.click(screen.getByRole('button', { name: /edit/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  const modal = within(dialog);

  expect(modal.getByLabelText(/output ratio/i)).toHaveValue('1:1');
  fireEvent.click(modal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(updateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        assetId: 'task-image',
        baseVersionId: 'task-image-v1',
        values: expect.objectContaining({
          tools: ['ax.nano_banana_image'],
          toolConfigs: {
            'ax.nano_banana_image': {
              model: 'gemini-3.1-flash-image-preview',
              aspect_ratio: '1:1',
              image_size: '1K',
            },
          },
        }),
      }),
    );
  });
});

test('edits a task in the configure task modal and persists changes', async () => {
  const { updateMutate } = arrangeTasksPage();

  selectTaskFromLibrary();
  fireEvent.click(screen.getByRole('button', { name: /edit/i }));
  const dialog = screen.getByRole('dialog', { name: /configure task/i });
  const modal = within(dialog);

  fireEvent.change(modal.getByLabelText(/^Name$/i), { target: { value: 'SEO Brief Revised' } });
  removePreset(modal, 1);
  fireEvent.change(modal.getByLabelText(/input presets/i), { target: { value: 'brand_name' } });
  fireEvent.click(modal.getByRole('button', { name: /remove crewai.web_search/i }));
  addTool(modal, 'crewai.file_read');
  fireEvent.click(modal.getByRole('button', { name: /save configuration/i }));

  await waitFor(() => {
    expect(updateMutate).toHaveBeenCalledWith({
      assetId: 'task-1',
      baseVersionId: 'task-v1',
      values: {
        name: 'SEO Brief Revised',
        description: 'Collect the main search intent signals. {brand_name}',
        expectedOutput: 'A concise SEO brief.',
        outputType: 'Raw',
        outputSchemaFields: [],
        asyncExecution: undefined,
        humanInput: undefined,
        markdown: undefined,
        guardrailMaxRetries: undefined,
        outputFile: '',
        createDirectory: undefined,
        inputPresets: ['website_url', 'brand_name'],
        tools: ['crewai.file_read'],
        toolConfigs: {
          'crewai.file_read': {},
        },
      },
    });
  });
});

test('opens delete dialog and confirms task deletion', async () => {
  const { deleteMutate } = arrangeTasksPage();

  selectTaskFromLibrary();
  fireEvent.click(screen.getByRole('button', { name: /delete/i }));
  const dialog = screen.getByRole('dialog', { name: /delete task/i });

  fireEvent.click(within(dialog).getByRole('button', { name: /confirm delete/i }));

  await waitFor(() => {
    expect(deleteMutate).toHaveBeenCalledWith('task-1');
  });
});

test('shows preset catalog error state and blocks task creation when the backend catalog is unavailable', async () => {
  taskHookMocks.useTasksLibrary.mockReturnValue({
    tasks: [],
    inputPresets: [],
    tools: [],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    presetCatalogError: new Error('catalog unavailable'),
    isPresetCatalogLoading: false,
    refetchPresetCatalog: vi.fn(),
  });
  taskHookMocks.useCreateTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  taskHookMocks.useUpdateTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  taskHookMocks.useDeleteTask.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });

  renderTasksPage();

  expect(screen.getByRole('button', { name: /\+ new/i })).toBeDisabled();
  expect(screen.getByText(/no tasks yet/i)).toBeInTheDocument();
});
