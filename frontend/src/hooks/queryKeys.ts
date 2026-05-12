const assetsAllKey = ['assets'] as const;
const runsListKey = ['runs'] as const;
const toolingAllKey = ['tooling'] as const;
const runtimeAllKey = ['runtime'] as const;
const flowGraphsAllKey = ['flow-graphs'] as const;
const taskInputPresetsAllKey = ['task-input-presets'] as const;
const llmCatalogAllKey = ['llm-catalog'] as const;
const capabilitiesAllKey = ['capabilities'] as const;
const connectedAccountsAllKey = ['connected-accounts'] as const;
const knowledgeAllKey = ['knowledge'] as const;

function normalizeVersionIds(versionIds: string[]) {
  return [...new Set(versionIds)].sort();
}

export const queryKeys = {
  assets: {
    all: () => assetsAllKey,
    detail: (assetId: string) => ['assets', assetId] as const,
    versions: (assetId: string) => ['assets', assetId, 'versions'] as const,
    version: (assetId: string, versionId: string) => ['assets', assetId, 'versions', versionId] as const,
  },
  runs: {
    list: () => runsListKey,
  },
  tooling: {
    all: () => toolingAllKey,
    toolCatalog: () => ['tooling', 'tool-catalog'] as const,
    skillCatalog: () => ['tooling', 'skill-catalog'] as const,
    versionTools: (versionId: string) => ['tooling', versionId, 'tools'] as const,
    versionSkills: (versionId: string) => ['tooling', versionId, 'skills'] as const,
  },
  runtime: {
    all: () => runtimeAllKey,
    credentials: () => ['runtime', 'credentials'] as const,
    versionCapabilities: (versionIds: string[]) => [
      'runtime',
      'version-capabilities',
      normalizeVersionIds(versionIds),
    ] as const,
  },
  flowGraphs: {
    all: () => flowGraphsAllKey,
    draft: (flowAssetId: string) => ['flow-graphs', flowAssetId, 'draft'] as const,
    publishedCrews: () => ['flow-graphs', 'published-crews'] as const,
  },
  taskInputPresets: {
    all: () => taskInputPresetsAllKey,
  },
  llmCatalog: {
    all: () => llmCatalogAllKey,
  },
  capabilities: {
    all: () => capabilitiesAllKey,
    executionActions: () => ['capabilities', 'execution-actions'] as const,
  },
  connectedAccounts: {
    all: () => connectedAccountsAllKey,
    providers: () => ['connected-accounts', 'providers'] as const,
  },
  knowledge: {
    all: () => knowledgeAllKey,
    version: (versionId: string) => ['knowledge', 'version', versionId] as const,
  },
} as const;
