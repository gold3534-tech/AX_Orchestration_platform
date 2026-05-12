CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS knowledge_chunks_workspace_item_idx
    ON knowledge_chunks (workspace_id, knowledge_item_id);

CREATE INDEX IF NOT EXISTS knowledge_chunks_item_index_idx
    ON knowledge_chunks (knowledge_item_id, chunk_index);

CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
    ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
