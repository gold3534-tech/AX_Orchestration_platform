export type CredentialProviderKey = 'openai' | 'anthropic' | 'google_gemini' | 'serper' | 'firecrawl';

export type CredentialProviderCard = {
  key: CredentialProviderKey;
  label: string;
  apiKeyLabel: string;
  description: string;
};

export type ConnectedAccountProviderCard = {
  key: 'google_workspace' | 'meta_instagram';
  label: string;
  authType: 'oauth2';
  description: string;
  capabilityKeys: string[];
};

export const credentialProviders: CredentialProviderCard[] = [
  {
    key: 'openai',
    label: 'OpenAI',
    apiKeyLabel: 'OpenAI API Key',
    description: 'Used for OpenAI LLMs, DALL-E, and Vision Tool execution.',
  },
  {
    key: 'anthropic',
    label: 'Anthropic',
    apiKeyLabel: 'Anthropic API Key',
    description: 'Used for Anthropic Claude model execution.',
  },
  {
    key: 'google_gemini',
    label: 'Google Gemini',
    apiKeyLabel: 'Google Gemini API Key',
    description: 'Used for Gemini model execution.',
  },
  {
    key: 'serper',
    label: 'Serper',
    apiKeyLabel: 'Serper API Key',
    description: 'Used by SerperDevTool for web search.',
  },
  {
    key: 'firecrawl',
    label: 'Firecrawl',
    apiKeyLabel: 'Firecrawl API Key',
    description: 'Used by Firecrawl website scraping tools.',
  },
];

export const connectedAccountProviders: ConnectedAccountProviderCard[] = [
  {
    key: 'google_workspace',
    label: 'Google Workspace',
    authType: 'oauth2',
    description: 'OAuth account used for Google Sheets and Drive capabilities.',
    capabilityKeys: ['sheets', 'drive', 'oauth2'],
  },
  {
    key: 'meta_instagram',
    label: 'Meta Instagram',
    authType: 'oauth2',
    description: 'OAuth account used for Instagram publish execution actions.',
    capabilityKeys: ['instagram_publish', 'oauth2'],
  },
];
