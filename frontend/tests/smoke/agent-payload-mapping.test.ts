import { agentDisplayName, toAgentAssetPayload } from '../../src/features/agents/hooks';

test('maps only defined agent runtime values to sparse top-level payload fields', () => {
  const payload = toAgentAssetPayload({
    role: 'Research Lead',
    goal: 'Collect market signals',
    backstory: '',
    verbose: false,
    allow_delegation: true,
    max_iter: undefined,
    embedder: 'text-embedding-3-small',
  });

  expect(agentDisplayName({ role: 'Research Lead' })).toBe('Research Lead');
  expect(payload).toEqual({
    role: 'Research Lead',
    goal: 'Collect market signals',
    verbose: false,
    allow_delegation: true,
    embedder: { model: 'text-embedding-3-small' },
  });
});

test('does not include database display name or tool attachments in agent payload', () => {
  const payload = toAgentAssetPayload({
    role: 'Runtime Role',
    goal: 'Run analysis',
    backstory: 'Built from the modal',
  });

  expect(agentDisplayName({ role: '' })).toBe('Untitled Agent');
  expect(payload).toEqual({
    role: 'Runtime Role',
    goal: 'Run analysis',
    backstory: 'Built from the modal',
  });
  expect(payload).not.toHaveProperty('name');
  expect(payload).not.toHaveProperty('display_name');
  expect(payload).not.toHaveProperty('tools');
  expect(payload).not.toHaveProperty('knowledgeSources');
  expect(payload).not.toHaveProperty('knowledge_sources');
});

test('allows no selected tools by keeping attachments outside the payload', () => {
  const payload = toAgentAssetPayload({
    role: 'No Tool Agent',
    goal: 'Work without attached tools',
    backstory: 'Uses model capabilities only',
  });

  expect(payload).toEqual({
    role: 'No Tool Agent',
    goal: 'Work without attached tools',
    backstory: 'Uses model capabilities only',
  });
});
