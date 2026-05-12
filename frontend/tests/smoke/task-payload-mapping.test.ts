import { toTaskAssetPayload, type TaskFormValues } from '../../src/features/tasks/hooks';

test('omits structured output fields for raw task output', () => {
  const values: TaskFormValues = {
    name: 'Raw Task',
    description: 'Write a plain summary',
    expectedOutput: 'Plain text summary',
    outputType: 'Raw',
    outputSchemaFields: [{ name: 'summary', type: 'str', description: 'Summary text', required: true }],
    asyncExecution: true,
    humanInput: false,
    markdown: true,
    guardrailMaxRetries: 2,
    outputFile: 'reports/summary.md',
    createDirectory: true,
    inputPresets: ['topic'],
    tools: ['crewai.web_search'],
  };

  const payload = toTaskAssetPayload(values);

  expect(payload).toEqual({
    description: 'Write a plain summary',
    expected_output: 'Plain text summary',
    async_execution: true,
    human_input: false,
    markdown: true,
    guardrail_max_retries: 2,
    output_file: 'reports/summary.md',
    create_directory: true,
    input_presets: ['topic'],
  });
  expect(payload).not.toHaveProperty('output_type');
  expect(payload).not.toHaveProperty('output_schema_fields');
  expect(payload).not.toHaveProperty('allow_crewai_context_tasks');
  expect(payload).not.toHaveProperty('allow_crewai_trigger_context');
  expect(payload).not.toHaveProperty('tools');
});

test('task payload omits graph-owned agent and trigger context fields', () => {
  const payload = toTaskAssetPayload({
    name: 'Task',
    description: 'Do the task.',
    expectedOutput: 'Done.',
    inputPresets: [],
    agent: 'Researcher',
    allowCrewaiTriggerContext: true,
  } as any);

  expect(payload).toEqual({
    description: 'Do the task.',
    expected_output: 'Done.',
    input_presets: [],
  });
  expect(payload).not.toHaveProperty('agent');
  expect(payload).not.toHaveProperty('allow_crewai_trigger_context');
});

test('preserves explicit false async execution and markdown values', () => {
  const values: TaskFormValues = {
    name: 'False Flags Task',
    description: 'Use explicit runtime flags',
    expectedOutput: 'Runtime result',
    outputType: 'Output JSON',
    outputSchemaFields: [{ name: 'result', type: 'str', description: 'Runtime result', required: true }],
    asyncExecution: false,
    humanInput: false,
    markdown: false,
    guardrailMaxRetries: undefined,
    outputFile: '',
    createDirectory: false,
    inputPresets: [],
    tools: [],
  };

  expect(toTaskAssetPayload(values)).toEqual({
    description: 'Use explicit runtime flags',
    expected_output: 'Runtime result',
    output_type: 'Output JSON',
    output_schema_fields: [{ name: 'result', type: 'str', description: 'Runtime result', required: true }],
    async_execution: false,
    human_input: false,
    markdown: false,
    create_directory: false,
    input_presets: [],
  });
});

test('defaults structured expected output from schema fields when omitted', () => {
  const payload = toTaskAssetPayload({
    name: 'Structured Task',
    description: 'Return structured content.',
    expectedOutput: '',
    outputType: 'Output JSON',
    outputSchemaFields: [
      { name: 'title', type: 'str', description: 'Title text', required: true },
      { name: 'content', type: 'str', description: 'Body text', required: true },
    ],
    inputPresets: [],
    tools: [],
  });

  expect(payload).toEqual({
    description: 'Return structured content.',
    expected_output: "A JSON object with 'title' and 'content' fields.",
    output_type: 'Output JSON',
    output_schema_fields: [
      { name: 'title', type: 'str', description: 'Title text', required: true },
      { name: 'content', type: 'str', description: 'Body text', required: true },
    ],
    input_presets: [],
  });
});
