import { describe, expect, it } from 'vitest';
import { toFormValues } from './AgentsPage';
import { mergeAgentAssetPayload, toAgentAssetPayload, type AgentFormValues } from './hooks';
import { findModelOption, legacyModelString, modelOptionsFromCatalog, parameterSpec } from './llmCatalog';

describe('agent payload mapping', () => {
  it('preserves structured LLM fields when opening an agent for edit', () => {
    const formValues = toFormValues({
      assetId: 'agent-1',
      versionId: 'version-1',
      name: 'Researcher',
      role: 'Researcher',
      goal: 'Find facts',
      backstory: 'Careful reviewer',
      photoUrl: '',
      allowDelegation: false,
      llm: 'gpt-4.1',
      llmProvider: 'openai',
      llmTemperature: 0.2,
      llmMaxTokens: 4096,
      function_calling_llm: 'gpt-4.1-mini',
      functionCallingLlmProvider: 'openai',
      tools: [],
      knowledgeSources: [],
      skills: [],
      status: 'draft',
    });

    expect(formValues).toMatchObject({
      llm: 'gpt-4.1',
      llmProvider: 'openai',
      llmTemperature: 0.2,
      llmMaxTokens: 4096,
      function_calling_llm: 'gpt-4.1-mini',
      functionCallingLlmProvider: 'openai',
    });
  });

  it('saves selected primary LLM as a structured object', () => {
    const values: AgentFormValues = {
      role: 'Researcher',
      goal: 'Find facts',
      backstory: 'Careful reviewer',
      llm: 'gpt-4.1',
      llmProvider: 'openai',
      llmTemperature: 0.2,
      llmMaxTokens: 4096,
    };

    expect(toAgentAssetPayload(values)).toMatchObject({
      llm: {
        provider: 'openai',
        model: 'gpt-4.1',
        temperature: 0.2,
        max_tokens: 4096,
      },
    });
  });

  it('omits primary LLM when no model is selected', () => {
    const values: AgentFormValues = {
      role: 'Researcher',
      goal: 'Find facts',
      backstory: 'Careful reviewer',
      llm: '',
      llmTemperature: 0.2,
      llmMaxTokens: 4096,
    };

    expect(toAgentAssetPayload(values)).not.toHaveProperty('llm');
  });

  it('saves function calling LLM as provider and model only', () => {
    const payload = mergeAgentAssetPayload(
      {},
      {
        role: 'Researcher',
        goal: 'Find facts',
        backstory: 'Careful reviewer',
        function_calling_llm: 'gpt-4.1-mini',
        functionCallingLlmProvider: 'openai',
        llmTemperature: 0.2,
        llmMaxTokens: 4096,
      },
    );

    expect(payload.function_calling_llm).toEqual({
      provider: 'openai',
      model: 'gpt-4.1-mini',
    });
  });

  it('preserves backend payload fields that are not modeled in the modal', () => {
    const payload = mergeAgentAssetPayload(
      {
        role: 'Researcher',
        goal: 'Find facts',
        backstory: 'Careful reviewer',
        system_template: 'system template',
        prompt_template: 'prompt template',
        response_template: 'response template',
        max_tokens: 4096,
        allow_code_execution: false,
        use_system_prompt: true,
        code_execution_mode: 'safe',
      },
      {
        role: 'Senior researcher',
        goal: 'Find sharper facts',
        backstory: 'Careful reviewer',
        cache: false,
      },
    );

    expect(payload).toMatchObject({
      role: 'Senior researcher',
      goal: 'Find sharper facts',
      backstory: 'Careful reviewer',
      cache: false,
      system_template: 'system template',
      prompt_template: 'prompt template',
      response_template: 'response template',
      max_tokens: 4096,
      allow_code_execution: false,
      use_system_prompt: true,
      code_execution_mode: 'safe',
    });
  });
});

describe('agent LLM catalog helpers', () => {
  it('reads legacy structured main_model payloads', () => {
    expect(legacyModelString({ provider: 'openai', main_model: 'openai/gpt-4o-mini' })).toBe('openai/gpt-4o-mini');
    expect(legacyModelString({ provider: 'openai', main_model: 'openai/gpt-4o-mini', model: 'openai/gpt-4o' })).toBe(
      'openai/gpt-4o-mini',
    );
  });

  it('maps catalog models to task 6 option shape', () => {
    const options = modelOptionsFromCatalog({
      providers: [
        {
          provider_key: 'openai',
          display_name: 'OpenAI',
          provider_type: 'hosted',
          enabled: true,
          sort_order: 1,
          metadata_json: {},
          models: [
            {
              model_key: 'openai/gpt-4.1',
              provider_key: 'openai',
              display_name: 'GPT-4.1',
              enabled: true,
              sort_order: 1,
              llm_metadata_json: {
                parameters: {
                  temperature: { supported: true, min: 0, max: 2, default: 0.7 },
                },
              },
            },
          ],
        },
      ],
    });

    expect(options).toEqual([
      {
        value: 'openai/gpt-4.1',
        label: 'GPT-4.1 · OpenAI',
        providerKey: 'openai',
        providerLabel: 'OpenAI',
        metadata: {
          parameters: {
            temperature: { supported: true, min: 0, max: 2, default: 0.7 },
          },
        },
      },
    ]);
    expect(findModelOption(options, 'openai/gpt-4.1')).toBe(options[0]);
    expect(parameterSpec(options[0], 'temperature')).toEqual({
      supported: true,
      min: 0,
      max: 2,
      default: 0.7,
    });
  });
});
