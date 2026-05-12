export type ConnectedAccountAuthType = 'oauth2' | 'api_key' | 'none' | (string & {});

export type ConnectedAccountProvider = {
  provider: string;
  display_name: string;
  label: string;
  env_var: string;
  auth_type: ConnectedAccountAuthType;
  connect_label: string;
  reconnect_label: string;
  supports_disconnect: boolean;
  supports_test_connection: boolean;
  capabilities: string[];
  capability_keys: string[];
  default_scopes: string[];
};

export type ConnectedAccountSummary = {
  id: string;
  provider: string;
  label: string;
  auth_type: ConnectedAccountAuthType;
  provider_account_id: string | null;
  provider_account_label: string | null;
  status: string;
  scopes: string[];
  missing_scopes: string[];
  expires_at: string | null;
  last_checked_at: string | null;
  capability_keys: string[];
  created_at: string;
  updated_at: string;
};

export type ConnectedAccountOAuthStartRequest = {
  provider: string;
  scopes: string[];
  redirect_path?: string | null;
};

export type ConnectedAccountOAuthStartResponse = {
  provider: string;
  authorization_url: string;
  state: string;
  expires_at: string;
};
