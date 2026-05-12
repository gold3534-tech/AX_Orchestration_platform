import { useQuery } from '@tanstack/react-query';
import { listCapabilities, type CapabilityCatalogItem } from '../../api/capabilities';
import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { PageHeader } from '../../components/platform/PageHeader';
import { queryKeys } from '../../hooks/queryKeys';

type ApiResult<TData> = {
  data?: TData;
  error?: unknown;
};

function unwrapResult<TData>({ data, error }: ApiResult<TData>) {
  if (error) {
    throw error;
  }

  return data;
}

function CapabilitySection({
  title,
  countLabel,
  capabilities,
}: {
  title: string;
  countLabel: string;
  capabilities: CapabilityCatalogItem[];
}) {
  return (
    <section className="pixel-panel bg-[#fff6df] p-5">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Capabilities</p>
          <h2 className="mt-1 text-xl font-black text-[#22170f]">{title}</h2>
        </div>
        <span className="rounded border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-1 text-xs font-bold text-stone-700">
          {countLabel}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {capabilities.map((capability) => (
          <article key={capability.key} className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4 shadow-[4px_4px_0_#7a5739]">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-lg font-black text-[#22170f]">{capability.label}</p>
                <p className="mt-1 break-all text-xs font-medium text-stone-500">{capability.key}</p>
                <p className="mt-2 text-sm leading-6 text-stone-700">{capability.description}</p>
              </div>
              <span className="shrink-0 rounded border border-[#7a5739]/50 px-2.5 py-1 text-xs font-bold text-stone-700">
                {capability.implementation_status}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="rounded border border-[#2f9b96] bg-[#e6f6f2] px-2.5 py-1 text-xs font-bold text-[#14645f]">
                {capability.type}
              </span>
              {capability.provider ? (
                <span className="rounded border border-[#7a5739]/40 bg-[#f8e8c8] px-2.5 py-1 text-xs font-semibold text-stone-700">
                  {capability.provider}
                </span>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ToolsLibraryPage() {
  const capabilitiesQuery = useQuery({
    queryKey: queryKeys.capabilities.all(),
    queryFn: async () => unwrapResult(await listCapabilities()) ?? [],
  });
  const capabilities = capabilitiesQuery.data ?? [];
  const executionActions = capabilities.filter((capability) => capability.type === 'Execution_Action');
  const agentTools = capabilities.filter((capability) => capability.type === 'agent_tool');

  return (
    <PageFrame sidebar={<Sidebar />}>
      <PageHeader
        title="Tools"
        description="CrewAI and custom tools available for Agent and Task versions."
      />

      {capabilitiesQuery.isLoading ? (
        <div className="rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] px-4 py-6 text-sm text-stone-500">
          Loading capabilities...
        </div>
      ) : null}

      {capabilitiesQuery.isError ? (
        <div className="rounded-md border-2 border-rose-300 bg-rose-50 px-4 py-6 text-sm text-rose-700">
          {capabilitiesQuery.error instanceof Error
            ? capabilitiesQuery.error.message
            : 'Unable to load the capability catalog.'}
        </div>
      ) : null}

      {!capabilitiesQuery.isLoading && !capabilitiesQuery.isError && capabilities.length === 0 ? (
        <div className="rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] px-4 py-6 text-sm text-stone-500">
          No capabilities registered yet.
        </div>
      ) : null}

      {!capabilitiesQuery.isLoading && !capabilitiesQuery.isError && capabilities.length > 0 ? (
        <>
          <CapabilitySection
            title="Agent tools"
            countLabel={`${agentTools.length} tools`}
            capabilities={agentTools}
          />
          <div className="mt-6">
            <CapabilitySection
              title="Execution actions"
              countLabel={`${executionActions.length} actions`}
              capabilities={executionActions}
            />
          </div>
        </>
      ) : null}
    </PageFrame>
  );
}
