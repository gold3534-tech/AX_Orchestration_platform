import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement, type PropsWithChildren } from 'react';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { queryKeys } from '../../src/hooks/queryKeys';
import type { paths } from '../../src/types/api.generated';

type Paths = keyof paths;

describe('api contract foundation', () => {
  afterEach(() => {
    vi.doUnmock('../../src/api/assets');
    vi.doUnmock('../../src/api/tooling');
    vi.unstubAllGlobals();
    window.localStorage.clear();
    vi.resetModules();
  });

  test('query keys remain stable across calls', () => {
    expect(queryKeys.assets.all()).toEqual(['assets']);
    expect(queryKeys.assets.all()).toBe(queryKeys.assets.all());
    expect(queryKeys.assets.detail('asset-123')).toEqual(['assets', 'asset-123']);
    expect(queryKeys.runs.list()).toEqual(['runs']);
    expect(queryKeys.flowGraphs.draft('flow-123')).toEqual(['flow-graphs', 'flow-123', 'draft']);
    expect(queryKeys.flowGraphs.publishedCrews()).toEqual(['flow-graphs', 'published-crews']);
  });

  test('version capability keys normalize version ordering', () => {
    const canonical = queryKeys.runtime.versionCapabilities(['version-b', 'version-a', 'version-a']);
    const reordered = queryKeys.runtime.versionCapabilities(['version-a', 'version-b']);

    expect(canonical).toEqual(reordered);
  });

  test('generated API includes provider credential routes', () => {
    const credentialPath: Paths = '/api/credentials/{provider}';

    expect(credentialPath).toBe('/api/credentials/{provider}');
  });

  test('provider credential helpers use generated PUT and DELETE routes', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(async (input) => {
      const request = input as Request;

      if (request.method === 'DELETE') {
        return new Response(null, { status: 204 });
      }

      return new Response(
        JSON.stringify({
          id: 'credential-1',
          provider: 'openai',
          label: 'OpenAI',
          enabled: true,
          created_at: '2026-04-28T00:00:00Z',
          updated_at: '2026-04-28T00:00:00Z',
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal('fetch', fetchSpy);

    const { deleteProviderCredential, upsertProviderCredential } = await import('../../src/api/credentials');

    await upsertProviderCredential('openai', { api_key: 'sk-test', label: 'OpenAI' });
    await deleteProviderCredential('openai');

    const putRequest = fetchSpy.mock.calls[0][0] as Request;
    const deleteRequest = fetchSpy.mock.calls[1][0] as Request;

    expect(putRequest.method).toBe('PUT');
    expect(putRequest.url).toBe('http://127.0.0.1/api/credentials/openai');
    expect(String(putRequest.body)).toContain('"api_key":"sk-test"');
    expect(String(putRequest.body)).toContain('"label":"OpenAI"');
    expect(deleteRequest.method).toBe('DELETE');
    expect(deleteRequest.url).toBe('http://127.0.0.1/api/credentials/openai');
  });

  test('the api client sends the stored auth token as a bearer header', async () => {
    window.localStorage.setItem('ai-oh.auth-token', 'smoke-token');
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(async () => new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);

    const { client } = await import('../../src/api/client');
    await client.GET('/api/assets');

    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const request = fetchSpy.mock.calls[0][0] as Request;
    expect(request.headers.get('Authorization')).toBe('Bearer smoke-token');
  });

  test('listAssets only forwards the generated query contract', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(async () => new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);

    const { listAssets } = await import('../../src/api/assets');
    await listAssets({ type: 'agent' });

    const request = fetchSpy.mock.calls[0][0] as Request;
    const searchParams = new URL(request.url).searchParams;

    expect(searchParams.get('type')).toBe('agent');
    expect([...searchParams.keys()]).toEqual(['type']);
  });

  test('listAssets supports the agent type shortcut for the agent library', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(async () => new Response('[]', { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);

    const { listAssets } = await import('../../src/api/assets');
    await listAssets('agent');

    const request = fetchSpy.mock.calls[0][0] as Request;

    expect(request.url).toContain('/api/assets?type=agent');
  });

  test('createAsset sends an agent payload through the canonical asset endpoint', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(
      async () => new Response(JSON.stringify({ id: 'asset-1' }), { status: 201 }),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const { createAsset } = await import('../../src/api/assets');
    await createAsset({
      type: 'agent',
      name: 'Creative Director',
      description: 'Leads story direction',
      payload: {
        role: '전략',
        goal: '메시지 전략 설계',
        backstory: '브랜드 리드',
        verbose: false,
      },
    });

    const request = fetchSpy.mock.calls[0][0] as Request;

    expect(request.url).toContain('/api/assets');
    expect(request.method).toBe('POST');
    expect(String(request.body)).toContain('"type":"agent"');
    expect(String(request.body)).toContain('"role":"전략"');
    expect(String(request.body)).toContain('"verbose":false');
  });

  test('flow creation payload uses only flow-level settings', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchMock = vi.fn<typeof fetch>(
      async () => new Response(JSON.stringify({ id: 'asset-1' }), { status: 201 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { createAsset } = await import('../../src/api/assets');
    await createAsset({
      type: 'flow',
      name: 'Lean Flow',
      description: 'Flow settings only',
      payload: {
        entry_method: 'run',
      },
    });

    const request = fetchMock.mock.calls.at(-1)?.[0] as Request;
    const body = JSON.parse(String(request.body));
    expect(body.payload).toEqual({ entry_method: 'run' });
  });

  test('agent hooks map canonical assets into the agent library contract', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(async (input) => {
      const requestUrl = typeof input === 'string' ? input : (input as Request).url;
      const url = new URL(requestUrl);

      if (url.pathname === '/api/tool-catalog') {
        return new Response(
          JSON.stringify([
            { tool_key: 'crewai.web_search', name: 'Web Search' },
            { tool_key: 'crewai.document_parser', name: 'Document Parser' },
          ]),
          { status: 200 },
        );
      }

      if (url.pathname === '/api/versions/agent-v1/tools') {
        return new Response(
          JSON.stringify([{ tool_key: 'crewai.web_search', name: 'Web Search', tool_config_json: { country: 'kr' } }]),
          { status: 200 },
        );
      }

      if (url.pathname === '/api/input-presets') {
        return new Response(
          JSON.stringify([
            {
              id: 'preset-website',
              key: 'website_url',
              label: 'Website URL',
              input_type: 'string',
              description: 'Target website.',
              is_active: true,
              sort_order: 1,
            },
          ]),
          { status: 200 },
        );
      }

      return new Response(
        JSON.stringify([
          {
            id: 'agent-1',
            type: 'agent',
            name: 'Research Lead',
            description: '조사',
            workspace_id: null,
            current_version: {
              id: 'agent-v1',
              version_no: 1,
              status: 'Ready',
              payload: {
                role: '조사',
                goal: '시장 신호를 수집합니다.',
                backstory: '탐색 중심 연구원',
                photo_url: 'https://example.com/research.png',
                allow_delegation: true,
                llm: 'gpt-4o',
                function_calling_llm: 'gpt-4o-mini',
                max_iter: 12,
                max_rpm: 7,
                max_execution_time: 90,
                verbose: true,
                reasoning: true,
                max_reasoning_attempts: 3,
                cache: true,
                respect_context_window: true,
                max_retry_limit: 4,
                multimodal: true,
                inject_date: true,
                date_format: '%d/%m/%Y',
                embedder: { model: 'text-embedding-3-small' },
                input_presets: ['website_url'],
                skills: ['Research'],
              },
              created_at: '2026-04-23T00:00:00Z',
              updated_at: '2026-04-23T00:00:00Z',
            },
            created_at: '2026-04-23T00:00:00Z',
            updated_at: '2026-04-23T00:00:00Z',
          },
        ]),
        { status: 200 },
      );
    });
    vi.stubGlobal('fetch', fetchSpy);

    const { useAgentsLibrary } = await import('../../src/features/agents/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result } = renderHook(() => useAgentsLibrary(), { wrapper });

    await waitFor(() => {
      expect(result.current.agents).toEqual([
        {
          assetId: 'agent-1',
          versionId: 'agent-v1',
          name: 'Research Lead',
          role: '조사',
          goal: '시장 신호를 수집합니다.',
          backstory: '탐색 중심 연구원',
          photoUrl: 'https://example.com/research.png',
          allowDelegation: true,
          llm: 'gpt-4o',
          function_calling_llm: 'gpt-4o-mini',
          max_iter: 12,
          max_rpm: 7,
          max_execution_time: 90,
          verbose: true,
          allow_delegation: true,
          reasoning: true,
          max_reasoning_attempts: 3,
          cache: true,
          respect_context_window: true,
          max_retry_limit: 4,
          multimodal: true,
          inject_date: true,
          date_format: '%d/%m/%Y',
          embedder: 'text-embedding-3-small',
          inputPresets: ['website_url'],
          tools: ['crewai.web_search'],
          toolConfigs: {
            'crewai.web_search': { country: 'kr' },
          },
          skills: ['Research'],
          status: 'Ready',
        },
      ]);
    });

    expect(result.current.tools).toEqual(['crewai.web_search', 'crewai.document_parser']);
    expect(result.current.inputPresets).toEqual([
      {
        key: 'website_url',
        label: 'Website URL',
        inputType: 'string',
        description: 'Target website.',
      },
    ]);
    expect(fetchSpy).toHaveBeenCalledTimes(4);
  });

  test('agent mutation hooks send canonical create update and delete requests', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi
      .fn<typeof fetch>()
      .mockImplementationOnce(
        async () =>
          new Response(
            JSON.stringify({
              id: 'agent-1',
              type: 'agent',
              name: 'Creative Director',
              current_version: {
                id: 'agent-v1',
                version_no: 1,
                status: 'Draft',
                payload: {},
                created_at: '2026-04-23T00:00:00Z',
                updated_at: '2026-04-23T00:00:00Z',
              },
              created_at: '2026-04-23T00:00:00Z',
              updated_at: '2026-04-23T00:00:00Z',
            }),
            { status: 201 },
          ),
      )
      .mockImplementationOnce(async () => new Response(JSON.stringify({ tool_key: 'crewai.web_search' }), { status: 201 }))
      .mockImplementationOnce(
        async () =>
          new Response(
            JSON.stringify({
              id: 'agent-1',
              type: 'agent',
              name: 'Creative Director',
              current_version: {
                id: 'agent-v2',
                version_no: 2,
                status: 'Ready',
                payload: {},
                created_at: '2026-04-23T00:00:00Z',
                updated_at: '2026-04-23T00:00:00Z',
              },
              created_at: '2026-04-23T00:00:00Z',
              updated_at: '2026-04-23T00:00:00Z',
            }),
            { status: 200 },
          ),
      )
      .mockImplementationOnce(async () => new Response(JSON.stringify({ tool_key: 'crewai.web_search' }), { status: 201 }))
      .mockImplementationOnce(async () => new Response(JSON.stringify({ tool_key: 'crewai.document_parser' }), { status: 201 }))
      .mockImplementationOnce(async () => new Response(null, { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);

    const { useCreateAgent, useDeleteAgent, useUpdateAgent } = await import('../../src/features/agents/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result: createResult } = renderHook(() => useCreateAgent(), { wrapper });
    await act(async () => {
      await createResult.current.mutateAsync({
        values: {
          role: '전략',
          goal: '메시지 전략 설계',
          backstory: '브랜드 리드',
          allow_delegation: true,
        },
        attachments: {
          tools: ['crewai.web_search'],
          toolConfigs: {
            'crewai.web_search': { country: 'kr' },
          },
        },
      });
    });

    const createRequest = fetchSpy.mock.calls[0][0] as Request;
    expect(createRequest.method).toBe('POST');
    expect(createRequest.url).toContain('/api/assets');
    expect(String(createRequest.body)).toContain('"type":"agent"');
    expect(String(createRequest.body)).toContain('"allow_delegation":true');
    expect(String(createRequest.body)).not.toContain('"photo_url"');
    expect(String(createRequest.body)).not.toContain('"input_presets"');
    expect(String(createRequest.body)).not.toContain('"tools"');
    expect(String(createRequest.body)).not.toContain('"skills"');

    const createAttachRequest = fetchSpy.mock.calls[1][0] as Request;
    const createAttachBody = JSON.parse(String(createAttachRequest.body));
    expect(createAttachRequest.method).toBe('POST');
    expect(createAttachRequest.url).toContain('/api/versions/agent-v1/tools');
    expect(createAttachBody).toEqual({
      tool_key: 'crewai.web_search',
      tool_config_json: { country: 'kr' },
    });

    const { result: updateResult } = renderHook(() => useUpdateAgent(), { wrapper });
    await act(async () => {
      await updateResult.current.mutateAsync({
        assetId: 'agent-1',
        baseVersionId: 'agent-v1',
        values: {
          role: '수정된 역할',
          goal: '수정된 목표',
          backstory: '수정된 배경',
          allow_delegation: false,
        },
        attachments: {
          tools: ['crewai.web_search', 'crewai.document_parser'],
          toolConfigs: {
            'crewai.web_search': { country: 'us' },
            'crewai.document_parser': { mode: 'ocr' },
          },
        },
      });
    });

    const updateRequest = fetchSpy.mock.calls[2][0] as Request;
    expect(updateRequest.method).toBe('PATCH');
    expect(updateRequest.url).toContain('/api/assets/agent-1');
    expect(String(updateRequest.body)).toContain('"base_version_id":"agent-v1"');
    expect(String(updateRequest.body)).toContain('"role":"수정된 역할"');
    expect(String(updateRequest.body)).toContain('"allow_delegation":false');
    expect(String(updateRequest.body)).not.toContain('"photo_url"');
    expect(String(updateRequest.body)).not.toContain('"input_presets"');
    expect(String(updateRequest.body)).not.toContain('"tools"');
    expect(String(updateRequest.body)).not.toContain('"skills"');

    const updateAttachRequests = fetchSpy.mock.calls.slice(3, 5).map((call) => call[0] as Request);
    expect(updateAttachRequests.map((request) => request.method)).toEqual(['POST', 'POST']);
    expect(updateAttachRequests.map((request) => request.url)).toEqual([
      expect.stringContaining('/api/versions/agent-v2/tools'),
      expect.stringContaining('/api/versions/agent-v2/tools'),
    ]);
    expect(updateAttachRequests.map((request) => String(request.body))).toEqual([
      JSON.stringify({ tool_key: 'crewai.web_search', tool_config_json: { country: 'us' } }),
      JSON.stringify({ tool_key: 'crewai.document_parser', tool_config_json: { mode: 'ocr' } }),
    ]);

    const { result: deleteResult } = renderHook(() => useDeleteAgent(), { wrapper });
    await act(async () => {
      await deleteResult.current.mutateAsync('agent-1');
    });

    const deleteRequest = fetchSpy.mock.calls[5][0] as Request;
    expect(deleteRequest.method).toBe('DELETE');
    expect(deleteRequest.url).toContain('/api/assets/agent-1');
  });

  test('agent mutation hooks throw when the api layer resolves with an error payload', async () => {
    const apiError = { detail: 'validation failed', status: 422 };

    vi.doMock('../../src/api/assets', async () => {
      const actual = await vi.importActual<typeof import('../../src/api/assets')>('../../src/api/assets');

      return {
        ...actual,
        createAsset: vi.fn(async () => ({ data: undefined, error: apiError })),
        updateAsset: vi.fn(async () => ({ data: undefined, error: apiError })),
        deleteAsset: vi.fn(async () => ({ data: undefined, error: apiError })),
      };
    });

    const { useCreateAgent, useDeleteAgent, useUpdateAgent } = await import('../../src/features/agents/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result: createResult } = renderHook(() => useCreateAgent(), { wrapper });
    await expect(
      createResult.current.mutateAsync({
        values: {
          role: '전략',
          goal: '메시지 전략 설계',
          backstory: '브랜드 리드',
          allow_delegation: false,
        },
        attachments: { tools: [] },
      }),
    ).rejects.toEqual(apiError);

    const { result: updateResult } = renderHook(() => useUpdateAgent(), { wrapper });
    await expect(
      updateResult.current.mutateAsync({
        assetId: 'agent-1',
        baseVersionId: 'agent-v1',
        values: {
          role: '수정된 역할',
          goal: '수정된 목표',
          backstory: '수정된 배경',
          allow_delegation: false,
        },
        attachments: { tools: [] },
      }),
    ).rejects.toEqual(apiError);

    const { result: deleteResult } = renderHook(() => useDeleteAgent(), { wrapper });
    await expect(deleteResult.current.mutateAsync('agent-1')).rejects.toEqual(apiError);

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  test('agent create and update invalidate after asset writes when tool attachment fails', async () => {
    const createAttachError = { detail: 'tool attach failed on create', status: 500 };
    const updateAttachError = { detail: 'tool attach failed on update', status: 500 };

    vi.doMock('../../src/api/assets', async () => {
      const actual = await vi.importActual<typeof import('../../src/api/assets')>('../../src/api/assets');

      return {
        ...actual,
        createAsset: vi.fn(async () => ({
          data: {
            id: 'agent-1',
            current_version: { id: 'agent-v1' },
          },
          error: undefined,
        })),
        updateAsset: vi.fn(async () => ({
          data: {
            id: 'agent-1',
            current_version: { id: 'agent-v2' },
          },
          error: undefined,
        })),
      };
    });
    vi.doMock('../../src/api/tooling', async () => {
      const actual = await vi.importActual<typeof import('../../src/api/tooling')>('../../src/api/tooling');

      return {
        ...actual,
        attachTool: vi.fn()
          .mockResolvedValueOnce({ data: undefined, error: createAttachError })
          .mockResolvedValueOnce({ data: undefined, error: updateAttachError }),
      };
    });

    const { useCreateAgent, useUpdateAgent } = await import('../../src/features/agents/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result: createResult } = renderHook(() => useCreateAgent(), { wrapper });
    await expect(
      createResult.current.mutateAsync({
        values: {
          role: '전략',
          goal: '메시지 전략 설계',
          backstory: '브랜드 리드',
          allow_delegation: false,
        },
        attachments: { tools: ['crewai.web_search'] },
      }),
    ).rejects.toBe(createAttachError);

    const { result: updateResult } = renderHook(() => useUpdateAgent(), { wrapper });
    await expect(
      updateResult.current.mutateAsync({
        assetId: 'agent-1',
        baseVersionId: 'agent-v1',
        values: {
          role: '수정된 역할',
          goal: '수정된 목표',
          backstory: '수정된 배경',
          allow_delegation: false,
        },
        attachments: { tools: ['crewai.document_parser'] },
      }),
    ).rejects.toBe(updateAttachError);

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy).toHaveBeenNthCalledWith(1, { queryKey: [...queryKeys.assets.all(), 'agent'] });
    expect(invalidateSpy).toHaveBeenNthCalledWith(2, { queryKey: [...queryKeys.assets.all(), 'agent'] });
  });

  test('successful agent writes invalidate the agent asset query', async () => {
    const createAsset = vi.fn(async () => ({
      data: {
        id: 'agent-1',
      },
      error: undefined,
    }));
    const updateAsset = vi.fn(async () => ({
      data: {
        id: 'agent-1',
      },
      error: undefined,
    }));
    const deleteAsset = vi.fn(async () => ({
      data: undefined,
      error: undefined,
    }));

    vi.doMock('../../src/api/assets', async () => {
      const actual = await vi.importActual<typeof import('../../src/api/assets')>('../../src/api/assets');

      return {
        ...actual,
        createAsset,
        updateAsset,
        deleteAsset,
      };
    });

    const { useCreateAgent, useDeleteAgent, useUpdateAgent } = await import('../../src/features/agents/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result: createResult } = renderHook(() => useCreateAgent(), { wrapper });
    await act(async () => {
      await createResult.current.mutateAsync({
        values: {
          role: '전략',
          goal: '메시지 전략 설계',
          backstory: '브랜드 리드',
          allow_delegation: false,
        },
        attachments: { tools: [] },
      });
    });

    const { result: updateResult } = renderHook(() => useUpdateAgent(), { wrapper });
    await act(async () => {
      await updateResult.current.mutateAsync({
        assetId: 'agent-1',
        baseVersionId: 'agent-v1',
        values: {
          role: '수정된 역할',
          goal: '수정된 목표',
          backstory: '수정된 배경',
          allow_delegation: false,
        },
        attachments: { tools: [] },
      });
    });

    const { result: deleteResult } = renderHook(() => useDeleteAgent(), { wrapper });
    await act(async () => {
      await deleteResult.current.mutateAsync('agent-1');
    });

    expect(invalidateSpy).toHaveBeenCalledTimes(3);
    expect(invalidateSpy).toHaveBeenNthCalledWith(1, { queryKey: [...queryKeys.assets.all(), 'agent'] });
    expect(invalidateSpy).toHaveBeenNthCalledWith(2, { queryKey: [...queryKeys.assets.all(), 'agent'] });
    expect(invalidateSpy).toHaveBeenNthCalledWith(3, { queryKey: [...queryKeys.assets.all(), 'agent'] });
  });

  test('task hooks map canonical assets into the task library contract', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi.fn<typeof fetch>(async (input) => {
      const requestUrl = typeof input === 'string' ? input : (input as Request).url;
      const url = new URL(requestUrl);

      if (url.pathname === '/api/input-presets') {
        return new Response(
          JSON.stringify([
            { key: 'website_url', label: '웹 사이트', input_type: 'url', description: '분석할 웹사이트 주소' },
          ]),
          { status: 200 },
        );
      }

      if (url.pathname === '/api/tool-catalog') {
        return new Response(
          JSON.stringify([
            { tool_key: 'crewai.web_search', name: 'Web Search' },
            { tool_key: 'crewai.file_read', name: 'File Read' },
          ]),
          { status: 200 },
        );
      }

      if (url.pathname === '/api/versions/task-v1/tools') {
        return new Response(
          JSON.stringify([{ tool_key: 'crewai.web_search', name: 'Web Search', tool_config_json: { country: 'kr' } }]),
          { status: 200 },
        );
      }

      return new Response(
        JSON.stringify([
          {
            id: 'task-1',
            type: 'task',
            name: 'SEO Brief',
            description: 'Collect search intent.',
            workspace_id: null,
            current_version: {
              id: 'task-v1',
              version_no: 1,
              status: 'Ready',
              payload: {
                description: 'Collect search intent.',
                expected_output: 'A concise SEO brief.',
                input_presets: ['website_url'],
              },
              created_at: '2026-04-23T00:00:00Z',
              updated_at: '2026-04-23T00:00:00Z',
            },
            created_at: '2026-04-23T00:00:00Z',
            updated_at: '2026-04-23T00:00:00Z',
          },
        ]),
        { status: 200 },
      );
    });
    vi.stubGlobal('fetch', fetchSpy);

    const { useTasksLibrary } = await import('../../src/features/tasks/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result } = renderHook(() => useTasksLibrary(), { wrapper });

    await waitFor(() => {
      expect(result.current.tasks).toEqual([
        {
          assetId: 'task-1',
          versionId: 'task-v1',
          name: 'SEO Brief',
          description: 'Collect search intent.',
          expectedOutput: 'A concise SEO brief.',
          outputType: 'Raw',
          outputSchemaFields: [],
          outputFile: '',
          inputPresets: ['website_url'],
          tools: ['crewai.web_search'],
          toolConfigs: {
            'crewai.web_search': { country: 'kr' },
          },
          summary: 'Collect search intent.',
          status: 'Ready',
        },
      ]);
      expect(result.current.inputPresets).toEqual([
        { key: 'website_url', label: '웹 사이트', inputType: 'url', description: '분석할 웹사이트 주소' },
      ]);
    });

    expect(result.current.tools).toEqual(['crewai.web_search', 'crewai.file_read']);
    expect(fetchSpy).toHaveBeenCalledTimes(4);
  });

  test('task mutation hooks send canonical create update and delete requests', async () => {
    import.meta.env.VITE_API_BASE_URL = 'http://127.0.0.1';
    const fetchSpy = vi
      .fn<typeof fetch>()
      .mockImplementationOnce(
        async () =>
          new Response(
            JSON.stringify({
              id: 'task-1',
              type: 'task',
              name: 'SEO Brief',
              current_version: {
                id: 'task-v1',
                version_no: 1,
                status: 'Draft',
                payload: {},
                created_at: '2026-04-23T00:00:00Z',
                updated_at: '2026-04-23T00:00:00Z',
              },
              created_at: '2026-04-23T00:00:00Z',
              updated_at: '2026-04-23T00:00:00Z',
            }),
            { status: 201 },
          ),
      )
      .mockImplementationOnce(async () => new Response(JSON.stringify({ tool_key: 'crewai.web_search' }), { status: 201 }))
      .mockImplementationOnce(
        async () =>
          new Response(
            JSON.stringify({
              id: 'task-1',
              type: 'task',
              name: 'SEO Brief Revised',
              current_version: {
                id: 'task-v2',
                version_no: 2,
                status: 'Ready',
                payload: {},
                created_at: '2026-04-23T00:00:00Z',
                updated_at: '2026-04-23T00:00:00Z',
              },
              created_at: '2026-04-23T00:00:00Z',
              updated_at: '2026-04-23T00:00:00Z',
            }),
            { status: 200 },
          ),
      )
      .mockImplementationOnce(async () => new Response(JSON.stringify({ tool_key: 'crewai.web_search' }), { status: 201 }))
      .mockImplementationOnce(async () => new Response(JSON.stringify({ tool_key: 'crewai.file_read' }), { status: 201 }))
      .mockImplementationOnce(async () => new Response(null, { status: 200 }));
    vi.stubGlobal('fetch', fetchSpy);

    const { useCreateTask, useDeleteTask, useUpdateTask } = await import('../../src/features/tasks/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result: createResult } = renderHook(() => useCreateTask(), { wrapper });
    await act(async () => {
      await createResult.current.mutateAsync({
        name: 'SEO Brief',
        description: 'Collect search intent.',
        expectedOutput: 'A concise SEO brief.',
        inputPresets: ['website_url'],
        tools: ['crewai.web_search'],
        toolConfigs: {
          'crewai.web_search': { country: 'kr' },
        },
      });
    });

    const createRequest = fetchSpy.mock.calls[0][0] as Request;
    expect(createRequest.method).toBe('POST');
    expect(createRequest.url).toContain('/api/assets');
    expect(String(createRequest.body)).toContain('"type":"task"');
    expect(String(createRequest.body)).toContain('"description":"Collect search intent."');
    expect(String(createRequest.body)).toContain('"expected_output":"A concise SEO brief."');
    expect(String(createRequest.body)).toContain('"input_presets":["website_url"]');
    expect(String(createRequest.body)).not.toContain('"tools"');

    const createAttachRequest = fetchSpy.mock.calls[1][0] as Request;
    const createAttachBody = JSON.parse(String(createAttachRequest.body));
    expect(createAttachRequest.method).toBe('POST');
    expect(createAttachRequest.url).toContain('/api/versions/task-v1/tools');
    expect(createAttachBody).toEqual({
      tool_key: 'crewai.web_search',
      tool_config_json: { country: 'kr' },
    });

    const { result: updateResult } = renderHook(() => useUpdateTask(), { wrapper });
    await act(async () => {
      await updateResult.current.mutateAsync({
        assetId: 'task-1',
        baseVersionId: 'task-v1',
        values: {
          name: 'SEO Brief Revised',
          description: 'Collect revised search intent.',
          expectedOutput: 'A revised SEO brief.',
          inputPresets: ['website_url', 'keyword'],
          tools: ['crewai.web_search', 'crewai.file_read'],
          toolConfigs: {
            'crewai.web_search': { country: 'us' },
            'crewai.file_read': { mode: 'read_only' },
          },
        },
      });
    });

    const updateRequest = fetchSpy.mock.calls[2][0] as Request;
    expect(updateRequest.method).toBe('PATCH');
    expect(updateRequest.url).toContain('/api/assets/task-1');
    expect(String(updateRequest.body)).toContain('"base_version_id":"task-v1"');
    expect(String(updateRequest.body)).toContain('"description":"Collect revised search intent."');
    expect(String(updateRequest.body)).toContain('"expected_output":"A revised SEO brief."');
    expect(String(updateRequest.body)).toContain('"input_presets":["website_url","keyword"]');
    expect(String(updateRequest.body)).not.toContain('"tools"');

    const updateAttachRequests = fetchSpy.mock.calls.slice(3, 5).map((call) => call[0] as Request);
    expect(updateAttachRequests.map((request) => request.method)).toEqual(['POST', 'POST']);
    expect(updateAttachRequests.map((request) => request.url)).toEqual([
      expect.stringContaining('/api/versions/task-v2/tools'),
      expect.stringContaining('/api/versions/task-v2/tools'),
    ]);
    expect(updateAttachRequests.map((request) => String(request.body))).toEqual([
      JSON.stringify({ tool_key: 'crewai.web_search', tool_config_json: { country: 'us' } }),
      JSON.stringify({ tool_key: 'crewai.file_read', tool_config_json: { mode: 'read_only' } }),
    ]);

    const { result: deleteResult } = renderHook(() => useDeleteTask(), { wrapper });
    await act(async () => {
      await deleteResult.current.mutateAsync('task-1');
    });

    const deleteRequest = fetchSpy.mock.calls[5][0] as Request;
    expect(deleteRequest.method).toBe('DELETE');
    expect(deleteRequest.url).toContain('/api/assets/task-1');
  });

  test('task create and update invalidate after asset writes when tool attachment fails', async () => {
    const createAttachError = { detail: 'tool attach failed on create', status: 500 };
    const updateAttachError = { detail: 'tool attach failed on update', status: 500 };

    vi.doMock('../../src/api/assets', async () => {
      const actual = await vi.importActual<typeof import('../../src/api/assets')>('../../src/api/assets');

      return {
        ...actual,
        createAsset: vi.fn(async () => ({
          data: {
            id: 'task-1',
            current_version: { id: 'task-v1' },
          },
          error: undefined,
        })),
        updateAsset: vi.fn(async () => ({
          data: {
            id: 'task-1',
            current_version: { id: 'task-v2' },
          },
          error: undefined,
        })),
      };
    });
    vi.doMock('../../src/api/tooling', async () => {
      const actual = await vi.importActual<typeof import('../../src/api/tooling')>('../../src/api/tooling');

      return {
        ...actual,
        attachTool: vi.fn()
          .mockResolvedValueOnce({ data: undefined, error: createAttachError })
          .mockResolvedValueOnce({ data: undefined, error: updateAttachError }),
      };
    });

    const { useCreateTask, useUpdateTask } = await import('../../src/features/tasks/hooks');

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = ({ children }: PropsWithChildren) =>
      createElement(QueryClientProvider, { client }, children);

    const { result: createResult } = renderHook(() => useCreateTask(), { wrapper });
    await expect(
      createResult.current.mutateAsync({
        name: 'SEO Brief',
        description: 'Collect search intent.',
        expectedOutput: 'A concise SEO brief.',
        inputPresets: ['website_url'],
        tools: ['crewai.web_search'],
      }),
    ).rejects.toBe(createAttachError);

    const { result: updateResult } = renderHook(() => useUpdateTask(), { wrapper });
    await expect(
      updateResult.current.mutateAsync({
        assetId: 'task-1',
        baseVersionId: 'task-v1',
        values: {
          name: 'SEO Brief Revised',
          description: 'Collect revised search intent.',
          expectedOutput: 'A revised SEO brief.',
          inputPresets: ['website_url'],
          tools: ['crewai.file_read'],
        },
      }),
    ).rejects.toBe(updateAttachError);

    expect(invalidateSpy).toHaveBeenCalledTimes(2);
    expect(invalidateSpy).toHaveBeenNthCalledWith(1, { queryKey: [...queryKeys.assets.all(), 'task'] });
    expect(invalidateSpy).toHaveBeenNthCalledWith(2, { queryKey: [...queryKeys.assets.all(), 'task'] });
  });
});
