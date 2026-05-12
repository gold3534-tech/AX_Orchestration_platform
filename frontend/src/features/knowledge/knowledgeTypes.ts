export type KnowledgeItem = {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  source_file_name: string;
  source_file_size: number;
  source_mime_type?: string | null;
  embedding_provider: string;
  embedding_model: string;
  chunk_count: number;
  attached_agent_count: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
};

export type KnowledgeCreatePayload = {
  name: string;
  description?: string | null;
  source_file_name: string;
  source_file_size: number;
  source_mime_type?: string | null;
  content: string;
};

export type KnowledgeUploadInput = {
  file: File;
  name?: string;
  description?: string;
};

export type VersionKnowledgeItemSummary = {
  id: string;
  name: string;
  status: string;
  source_file_name: string;
};

export type VersionKnowledgeBinding = {
  id: string;
  version_id: string;
  knowledge_item_id: string;
  sort_order: number;
  knowledge: VersionKnowledgeItemSummary;
  created_at: string;
};
