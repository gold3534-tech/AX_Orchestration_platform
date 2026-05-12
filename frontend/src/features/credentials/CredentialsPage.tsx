import { Eye, EyeOff, KeyRound, Link as LinkIcon } from 'lucide-react';
import { useMemo, useRef, useState, type FormEvent } from 'react';
import { PageFrame } from '../../components/layout/PageFrame';
import { Sidebar } from '../../components/layout/Sidebar';
import { PageHeader } from '../../components/platform/PageHeader';
import { ActionFeedbackDialog } from '../../components/shared/ActionFeedbackDialog';
import { CrudModal } from '../../components/shared/CrudModal';
import { DeleteConfirm } from '../../components/shared/DeleteConfirm';
import {
  connectedAccountProviders,
  credentialProviders,
  type CredentialProviderCard,
} from './providerRegistry';
import type { ConnectedAccountProvider, ConnectedAccountSummary } from './connectedAccountTypes';
import {
  useConnectedAccountProviders,
  useConnectedAccounts,
  useCredentials,
  useDeleteCredential,
  useDisconnectConnectedAccount,
  useStartConnectedAccountOAuth,
  useUpsertCredential,
} from './hooks';
import { redirectToOAuthAuthorization } from './oauthRedirect';

function formatCredentialMutationError(error: unknown, fallback: string) {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
      return detail;
    }
  }

  return fallback;
}

function connectedAccountDescription(provider: ConnectedAccountProvider) {
  const registryProvider = connectedAccountProviders.find((item) => item.key === provider.provider);
  return registryProvider?.description ?? `${provider.label} OAuth account for AX capabilities.`;
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function connectedAccountCapabilities(provider: ConnectedAccountProvider) {
  const providerCapabilityKeys = stringList(provider.capability_keys);
  const capabilityKeys = providerCapabilityKeys.length > 0 ? providerCapabilityKeys : stringList(provider.capabilities);
  return capabilityKeys.join(', ');
}

function connectedAccountDisplayName(account: ConnectedAccountSummary | undefined) {
  return account?.provider_account_label || account?.provider_account_id || null;
}

function connectedAccountId(account: ConnectedAccountSummary | undefined) {
  if (!account?.provider_account_id) {
    return null;
  }
  if (account.provider_account_id === account.provider_account_label) {
    return null;
  }
  return account.provider_account_id;
}

export function CredentialsPage() {
  const { credentialsByProvider, isLoading, isError, error } = useCredentials();
  const upsertCredential = useUpsertCredential();
  const deleteCredential = useDeleteCredential();
  const connectedProvidersQuery = useConnectedAccountProviders();
  const connectedAccountsQuery = useConnectedAccounts();
  const startConnectedAccountOAuth = useStartConnectedAccountOAuth();
  const disconnectConnectedAccount = useDisconnectConnectedAccount();
  const oauthStartInFlightRef = useRef(false);
  const [editingProvider, setEditingProvider] = useState<CredentialProviderCard | null>(null);
  const [deleteProvider, setDeleteProvider] = useState<CredentialProviderCard | null>(null);
  const [disconnectProvider, setDisconnectProvider] = useState<ConnectedAccountProvider | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [isApiKeyVisible, setIsApiKeyVisible] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  function closeEditor() {
    setEditingProvider(null);
    setApiKey('');
    setIsApiKeyVisible(false);
  }

  function openEditor(provider: CredentialProviderCard) {
    setEditingProvider(provider);
    setApiKey('');
    setIsApiKeyVisible(false);
  }

  async function submitCredential(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const submittedApiKey = apiKey.trim();
    if (!editingProvider || !submittedApiKey) {
      return;
    }
    setApiKey('');

    try {
      await upsertCredential.mutateAsync({
        provider: editingProvider.key,
        apiKey: submittedApiKey,
        label: editingProvider.apiKeyLabel,
      });
      closeEditor();
    } catch (mutationError) {
      setFeedback(formatCredentialMutationError(mutationError, 'Credential could not be saved.'));
    }
  }

  async function confirmDelete() {
    if (!deleteProvider) {
      return;
    }

    try {
      await deleteCredential.mutateAsync(deleteProvider.key);
      setDeleteProvider(null);
    } catch (mutationError) {
      setFeedback(formatCredentialMutationError(mutationError, 'Credential could not be deleted.'));
    }
  }

  const oauthProviders = useMemo<ConnectedAccountProvider[]>(() => {
    if (connectedProvidersQuery.providers.length > 0) {
      return connectedProvidersQuery.providers;
    }
    return connectedAccountProviders.map((provider) => ({
      provider: provider.key,
      display_name: provider.label,
      label: provider.label,
      env_var: '',
      auth_type: provider.authType,
      connect_label: `Connect ${provider.label}`,
      reconnect_label: `Reconnect ${provider.label}`,
      supports_disconnect: true,
      supports_test_connection: true,
      capabilities: provider.capabilityKeys,
      capability_keys: provider.capabilityKeys,
      default_scopes: [],
    }));
  }, [connectedProvidersQuery.providers]);

  async function startOAuth(provider: ConnectedAccountProvider) {
    if (startConnectedAccountOAuth.isPending || oauthStartInFlightRef.current) {
      return;
    }

    oauthStartInFlightRef.current = true;
    try {
      const result = await startConnectedAccountOAuth.mutateAsync({
        provider: provider.provider,
        scopes: stringList(provider.default_scopes),
        redirect_path: '/build/credentials',
      });
      if (!result?.authorization_url) {
        setFeedback('OAuth authorization URL was not returned.');
        return;
      }
      redirectToOAuthAuthorization(result.authorization_url);
    } catch (mutationError) {
      setFeedback(formatCredentialMutationError(mutationError, 'Connected account OAuth could not be started.'));
    } finally {
      oauthStartInFlightRef.current = false;
    }
  }

  async function confirmDisconnectConnectedAccount() {
    if (!disconnectProvider) {
      return;
    }

    try {
      await disconnectConnectedAccount.mutateAsync(disconnectProvider.provider);
      setDisconnectProvider(null);
    } catch (mutationError) {
      setFeedback(formatCredentialMutationError(mutationError, 'Connected account could not be disconnected.'));
    }
  }

  return (
    <PageFrame sidebar={<Sidebar />}>
      <PageHeader
        title="Credentials"
        description="Connect provider API keys for CrewAI runs. Secrets are write-only and never displayed after saving."
      />

      {isLoading ? (
        <p className="mb-4 rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] p-4 text-sm text-stone-500">
          Loading credentials...
        </p>
      ) : null}
      {isError ? (
        <p className="mb-4 rounded-md border-2 border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
          {error instanceof Error ? error.message : 'Unable to load credentials.'}
        </p>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {credentialProviders.map((provider) => {
          const credential = credentialsByProvider.get(provider.key);
          const connected = Boolean(credential?.enabled);

          return (
            <article key={provider.key} className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-5 shadow-[4px_4px_0_#7a5739]">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <KeyRound aria-hidden="true" className="h-4 w-4 shrink-0 text-[#2f9b96]" />
                    <h2 className="text-lg font-black text-[#22170f]">{provider.label}</h2>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-stone-600">{provider.description}</p>
                </div>
                <span
                  className={[
                    'shrink-0 rounded border px-2.5 py-1 text-xs font-bold',
                    connected
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-stone-200 bg-stone-50 text-stone-600',
                  ].join(' ')}
                >
                  {connected ? 'Connected' : 'Not connected'}
                </span>
              </div>

              {credential ? (
                <p className="mt-3 text-xs text-stone-500">Updated {new Date(credential.updated_at).toLocaleString()}</p>
              ) : null}

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => openEditor(provider)}
                  className="pixel-button border-[#2f9b96] bg-[#e6f6f2] px-4 py-2 text-sm font-bold text-[#14645f] hover:bg-[#d8f0ec]"
                >
                  {connected ? `Replace ${provider.label}` : `Connect ${provider.label}`}
                </button>
                <button
                  type="button"
                  disabled
                  className="pixel-button border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-stone-400"
                >
                  Test connection
                </button>
                {connected ? (
                  <button
                    type="button"
                    onClick={() => setDeleteProvider(provider)}
                    className="pixel-button border-rose-700 bg-[#fffaf0] px-4 py-2 text-sm font-bold text-rose-700 hover:bg-rose-50"
                  >
                    Delete {provider.label}
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </section>

      <section className="pixel-panel mt-8 bg-[#fff6df] p-5">
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#2f9b96]">Connected Accounts</p>
            <h2 className="mt-1 text-xl font-black text-[#22170f]">OAuth providers</h2>
          </div>
          <span className="rounded border-2 border-[#7a5739] bg-[#fffaf0] px-3 py-1 text-xs font-bold text-stone-700">
            {oauthProviders.length} providers
          </span>
        </div>

        {connectedProvidersQuery.isLoading || connectedAccountsQuery.isLoading ? (
          <p className="mb-4 rounded-md border-2 border-dashed border-[#7a5739] bg-[#fffaf0] p-4 text-sm text-stone-500">
            Loading connected accounts...
          </p>
        ) : null}
        {connectedProvidersQuery.isError ? (
          <p className="mb-4 rounded-md border-2 border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
            {connectedProvidersQuery.error instanceof Error
              ? connectedProvidersQuery.error.message
              : 'Unable to load connected account providers.'}
          </p>
        ) : null}
        {connectedAccountsQuery.isError ? (
          <p className="mb-4 rounded-md border-2 border-rose-300 bg-rose-50 p-4 text-sm text-rose-700">
            {connectedAccountsQuery.error instanceof Error
              ? connectedAccountsQuery.error.message
              : 'Unable to load connected accounts.'}
          </p>
        ) : null}

        <div className="grid gap-3 md:grid-cols-2">
          {oauthProviders.map((provider) => {
            const account = connectedAccountsQuery.accountsByProvider.get(provider.provider);
            const connected = Boolean(account);
            const displayName = connectedAccountDisplayName(account);
            const providerAccountId = connectedAccountId(account);
            const missingScopes = stringList(account?.missing_scopes);
            const isStarting =
              startConnectedAccountOAuth.isPending &&
              startConnectedAccountOAuth.variables?.provider === provider.provider;

            return (
              <article key={provider.provider} className="rounded-md border-2 border-[#7a5739] bg-[#fffaf0] p-4 shadow-[3px_3px_0_rgba(122,87,57,0.35)]">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <LinkIcon aria-hidden="true" className="h-4 w-4 shrink-0 text-[#2f9b96]" />
                      <h3 className="text-base font-black text-[#22170f]">{provider.label}</h3>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-stone-600">{connectedAccountDescription(provider)}</p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    {connected ? (
                      <span className="rounded border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-700">
                        Connected
                      </span>
                    ) : null}
                    <span className="rounded border border-[#7a5739]/40 bg-[#f8e8c8] px-2.5 py-1 text-xs font-bold text-stone-600">
                      {provider.auth_type}
                    </span>
                  </div>
                </div>

                {displayName ? (
                  <div className="mt-3 border-l-2 border-[#2f9b96] pl-3">
                    <p className="text-sm font-semibold text-stone-900">{displayName}</p>
                    {providerAccountId ? <p className="mt-1 break-all text-xs text-stone-500">{providerAccountId}</p> : null}
                  </div>
                ) : null}

                {account ? (
                  <div className="mt-3 space-y-1 text-xs text-stone-500">
                    <p>Updated {new Date(account.updated_at).toLocaleString()}</p>
                    {missingScopes.length > 0 ? (
                      <p className="break-words text-amber-700">Missing scopes: {missingScopes.join(', ')}</p>
                    ) : null}
                  </div>
                ) : null}

                <p className="mt-3 break-words text-xs text-stone-500">{connectedAccountCapabilities(provider)}</p>

                <div className="mt-5 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={startConnectedAccountOAuth.isPending}
                    onClick={() => void startOAuth(provider)}
                    className="pixel-button border-[#2f9b96] bg-[#e6f6f2] px-4 py-2 text-sm font-bold text-[#14645f] hover:bg-[#d8f0ec] disabled:opacity-50"
                  >
                    {isStarting ? 'Starting...' : connected ? provider.reconnect_label : provider.connect_label}
                  </button>
                  {connected && provider.supports_disconnect ? (
                    <button
                      type="button"
                      onClick={() => setDisconnectProvider(provider)}
                      className="pixel-button border-rose-700 bg-[#fffaf0] px-4 py-2 text-sm font-bold text-rose-700 hover:bg-rose-50"
                    >
                      Disconnect
                    </button>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <CrudModal
        open={Boolean(editingProvider)}
        title={
          editingProvider
            ? `${credentialsByProvider.has(editingProvider.key) ? 'Replace' : 'Connect'} ${editingProvider.label}`
            : 'Credential'
        }
        onClose={closeEditor}
        maxWidthClassName="max-w-lg"
      >
        <form onSubmit={submitCredential} className="space-y-4">
          <label className="block text-sm font-medium text-stone-700">
            API key
            <span className="mt-2 flex overflow-hidden rounded-md border-2 border-[#7a5739] bg-[#fffaf0] focus-within:border-[#2f9b96] focus-within:ring-2 focus-within:ring-[#2f9b96]/25">
              <input
                type={isApiKeyVisible ? 'text' : 'password'}
                autoComplete="new-password"
                spellCheck={false}
                autoCapitalize="none"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                className="min-w-0 flex-1 border-0 bg-[#fffaf0] px-3 py-2 font-mono text-sm text-stone-950 outline-none"
              />
              <button
                type="button"
                aria-label={isApiKeyVisible ? 'Hide key' : 'Show key'}
                title={isApiKeyVisible ? 'Hide key' : 'Show key'}
                onClick={() => setIsApiKeyVisible((visible) => !visible)}
                className="flex h-10 w-10 shrink-0 items-center justify-center border-l-2 border-[#7a5739] text-stone-500 hover:bg-[#ffe6b3] hover:text-stone-900"
              >
                {isApiKeyVisible ? (
                  <EyeOff aria-hidden="true" className="h-4 w-4" />
                ) : (
                  <Eye aria-hidden="true" className="h-4 w-4" />
                )}
              </button>
            </span>
          </label>
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={closeEditor}
              className="pixel-button border-[#7a5739] bg-[#fffaf0] px-4 py-2 text-sm font-bold text-[#22170f] hover:bg-[#ffe6b3]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!apiKey.trim() || upsertCredential.isPending}
              className="pixel-button bg-[#2f9b96] px-4 py-2 text-sm font-bold text-white hover:bg-[#3fb0aa] disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </form>
      </CrudModal>

      <DeleteConfirm
        open={Boolean(deleteProvider)}
        title={deleteProvider ? `Delete ${deleteProvider.label} credential` : 'Delete credential'}
        message="This disconnects the provider for future runs. Existing run history remains unchanged."
        confirmLabel="Disconnect"
        isPending={deleteCredential.isPending}
        onCancel={() => setDeleteProvider(null)}
        onConfirm={confirmDelete}
      />

      <DeleteConfirm
        open={Boolean(disconnectProvider)}
        title={disconnectProvider ? `Disconnect ${disconnectProvider.label}` : 'Disconnect account'}
        message="This disconnects the OAuth account for future runs. Existing run history remains unchanged."
        confirmLabel="Disconnect"
        isPending={disconnectConnectedAccount.isPending}
        onCancel={() => setDisconnectProvider(null)}
        onConfirm={confirmDisconnectConnectedAccount}
      />

      <ActionFeedbackDialog
        open={Boolean(feedback)}
        tone="danger"
        title="Credential action failed"
        description={feedback}
        onCancel={() => setFeedback(null)}
      />
    </PageFrame>
  );
}
