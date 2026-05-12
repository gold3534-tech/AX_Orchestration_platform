import { describe, expect, it } from 'vitest';
import {
  createCrewFormValues,
  mergeCrewAssetPayload,
  toCrewAssetPayload,
  type CrewListItem,
} from './hooks';

const runtimeBooleanKeys = ['verbose', 'planning', 'memory', 'cache', 'stream', 'tracing', 'checkpoint'];

function crewWithPayload(payload: Record<string, unknown>): CrewListItem {
  const process = payload.process === 'hierarchical' ? 'hierarchical' : 'sequential';

  return {
    assetId: 'crew-asset-1',
    versionId: 'crew-version-1',
    versionNo: 1,
    name: 'Existing crew',
    description: '',
    process,
    processType: process,
    managerAgentAssetId: '',
    managerAgentName: '',
    managerLlm: '',
    managerLlmModel: '',
    functionCallingLlm: '',
    verbose: false,
    planning: false,
    memory: false,
    memoryEnabled: false,
    cache: false,
    stream: false,
    tracing: false,
    checkpoint: false,
    outputLogFile: '',
    planningLlm: '',
    chatLlm: '',
    embedder: '',
    isVerbose: false,
    payload,
    status: 'draft',
  };
}

describe('crew payload mapping', () => {
  it('omits untouched optional runtime booleans from create payloads', () => {
    const payload = toCrewAssetPayload({
      ...createCrewFormValues(),
      name: 'Sparse runtime crew',
    });

    expect(runtimeBooleanKeys.filter((key) => key in payload)).toEqual([]);
  });

  it('includes explicit false runtime booleans selected in the modal', () => {
    const payload = toCrewAssetPayload({
      ...createCrewFormValues(),
      name: 'Explicit false runtime crew',
      cache: false,
    });

    expect(payload).toHaveProperty('cache', false);
  });

  it('preserves existing edit payload values while overlaying modal runtime changes', () => {
    const currentPayload = {
      verbose: false,
      cache: true,
      stream: true,
      custom_runtime_field: 'keep me',
    };
    const formValues = createCrewFormValues(crewWithPayload(currentPayload));

    const payload = mergeCrewAssetPayload(currentPayload, {
      ...formValues,
      cache: false,
      stream: undefined,
    });

    expect(payload).toMatchObject({
      verbose: false,
      cache: false,
      stream: true,
      custom_runtime_field: 'keep me',
    });
    expect(payload).not.toHaveProperty('planning');
    expect(payload).not.toHaveProperty('memory');
    expect(payload).not.toHaveProperty('tracing');
    expect(payload).not.toHaveProperty('checkpoint');
  });

  it('emits manager llm for hierarchical manager llm crews', () => {
    const payload = toCrewAssetPayload({
      ...createCrewFormValues(),
      name: 'Hierarchical manager llm crew',
      process: 'hierarchical',
      managerLlm: 'gpt-4o-mini',
    });

    expect(payload).toMatchObject({
      process: 'hierarchical',
      manager_llm: 'gpt-4o-mini',
    });
    expect(payload).not.toHaveProperty('manager_agent_asset_id');
  });

  it('adds the default manager llm to hierarchical create payloads when unset', () => {
    const payload = toCrewAssetPayload({
      ...createCrewFormValues(),
      name: 'Hierarchical default manager llm crew',
      process: 'hierarchical',
      managerLlm: '',
    });

    expect(payload).toMatchObject({
      process: 'hierarchical',
      manager_llm: 'openai/gpt-4o-mini',
    });
  });

  it('adds the default manager llm to hierarchical edit payloads when unset', () => {
    const currentPayload = {
      process: 'hierarchical',
      manager_agent_asset_id: 'agent-asset-1',
    };
    const formValues = createCrewFormValues(crewWithPayload(currentPayload));

    const payload = mergeCrewAssetPayload(currentPayload, {
      ...formValues,
      process: 'hierarchical',
      managerAgentAssetId: 'agent-asset-1',
      managerLlm: '',
    });

    expect(payload).toMatchObject({
      process: 'hierarchical',
      manager_agent_asset_id: 'agent-asset-1',
      manager_llm: 'openai/gpt-4o-mini',
    });
  });

  it('adds the default manager llm to hierarchical create payloads when it is whitespace-only', () => {
    const payload = toCrewAssetPayload({
      ...createCrewFormValues(),
      name: 'Hierarchical whitespace manager llm crew',
      process: 'hierarchical',
      managerLlm: '   ',
    });

    expect(payload).toMatchObject({
      process: 'hierarchical',
      manager_llm: 'openai/gpt-4o-mini',
    });
  });

  it('adds the default manager llm to hierarchical edit payloads when it is whitespace-only', () => {
    const currentPayload = {
      process: 'hierarchical',
      manager_llm: 'gpt-4o-mini',
      manager_agent_asset_id: 'agent-asset-1',
    };
    const formValues = createCrewFormValues(crewWithPayload(currentPayload));

    const payload = mergeCrewAssetPayload(currentPayload, {
      ...formValues,
      process: 'hierarchical',
      managerAgentAssetId: 'agent-asset-1',
      managerLlm: '   ',
    });

    expect(payload).toMatchObject({
      process: 'hierarchical',
      manager_agent_asset_id: 'agent-asset-1',
      manager_llm: 'openai/gpt-4o-mini',
    });
  });

  it('hydrates hierarchical manager llm from main_model payload objects', () => {
    const formValues = createCrewFormValues(
      crewWithPayload({
        process: 'hierarchical',
        manager_llm: { provider: 'openai', main_model: 'gpt-4o-mini' },
      }),
    );

    expect(formValues.process).toBe('hierarchical');
    expect(formValues.managerLlm).toBe('gpt-4o-mini');
  });
});
