# RAG (Retrieval Augmented Generation) Setup Guide

## Overview
This setup enables RAG capabilities for the `project_document` table, allowing for fast semantic search and retrieval of relevant document content for agent prompts.

## Prerequisites

### 1. Install pgvector Extension

**On your PostgreSQL server, run:**
```sql
-- Connect to your database
CREATE EXTENSION IF NOT EXISTS vector;
```

**For Docker PostgreSQL:**
```bash
# Use a PostgreSQL image with pgvector
docker run -d \
  --name postgres-rag \
  -e POSTGRES_PASSWORD=yourpassword \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

**For Ubuntu/Debian:**
```bash
sudo apt-get install postgresql-16-pgvector
```

**For macOS (Homebrew):**
```bash
brew install pgvector
```

## Database Setup

### Step 1: Create Extension
```sql
-- Run Extensions/pgvector.sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Step 2: Update project_document Table
```sql
-- Run the updated Tables/project_document.sql
-- This adds embedding_status, embedding_model, embedded_at, chunk_count columns
```

### Step 3: Create document_chunk Table
```sql
-- Run Tables/document_chunk.sql
-- This creates the table for storing document chunks with embeddings
```

### Step 4: Create Functions and Procedures
```sql
-- Run Functions/fn_chunk_document.sql
-- Run Functions/fn_search_documents_rag.sql
-- Run Functions/fn_get_relevant_context.sql
-- Run Procedures/sp_store_document_chunks.sql
```

## n8n Workflow Integration

### Workflow for Document Embedding

Add these nodes to your workflow after document creation/serialization:

#### **Node 1: Chunk Document**
**Node Type:** Postgres
**Query:**
```sql
SELECT main.fn_chunk_document(
    {{ $json.document_id }},
    1000,  -- chunk_size (characters)
    200    -- chunk_overlap (characters)
) AS result;
```

#### **Node 2: Generate Embeddings (HTTP Request to OpenAI/Cohere/etc.)**
**Node Type:** HTTP Request
**Method:** POST
**URL:** `https://api.openai.com/v1/embeddings`
**Authentication:** Bearer Token
**Headers:**
- `Content-Type: application/json`
**Body (Expression Mode):**
```javascript
{
  "model": "text-embedding-3-small",
  "input": $json.result.chunks.map(chunk => chunk.chunk_text)
}
```

#### **Node 3: Map Embeddings to Chunks**
**Node Type:** Code (JavaScript)
**Code:**
```javascript
const chunkResult = $('Postgres').item.json.result;
const embeddings = $input.item.json.data; // From OpenAI API response

const chunksWithEmbeddings = chunkResult.chunks.map((chunk, index) => ({
  ...chunk,
  embedding: embeddings[index]?.embedding || null,
  token_count: embeddings[index]?.usage?.total_tokens || null
}));

return [{
  json: {
    document_id: chunkResult.document_id,
    chunks: chunksWithEmbeddings,
    embedding_model: 'text-embedding-3-small'
  }
}];
```

#### **Node 4: Store Chunks with Embeddings**
**Node Type:** Postgres
**Query:**
```sql
CALL main.sp_store_document_chunks(
    {{ $json.document_id }},
    '{{ JSON.stringify($json.chunks) }}'::jsonb,
    '{{ $json.embedding_model }}',
    'system'
);
```

## Using RAG for Agent Prompts

### Retrieving Relevant Context

**Option 1: Search and Get Context (for prompts)**
```sql
-- First, get embedding for your query (via API or function)
-- Then retrieve relevant context
SELECT main.fn_get_relevant_context(
    '[...your query embedding vector...]'::vector(1536),
    {{ project_id }},
    5  -- number of chunks to retrieve
) AS context_text;
```

**Option 2: Search with Full Details**
```sql
SELECT main.fn_search_documents_rag(
    '[...your query embedding vector...]'::vector(1536),
    {{ project_id }},
    10,  -- limit
    0.7  -- similarity threshold (0-1)
) AS search_results;
```

### Integration in Agent Workflow

**In your n8n workflow, before sending agent prompts:**

1. **Get Query Embedding:**
   - Call embedding API with your query/prompt
   - Extract the embedding vector

2. **Retrieve Relevant Context:**
   - Use `fn_get_relevant_context()` or `fn_search_documents_rag()`
   - Include retrieved context in the agent prompt

3. **Enhanced Prompt Example:**
```
You are a Cursor cloud agent.

Relevant Context from Project Documents:
{{ context_text }}

Your task: [original task description]
```

## Vector Embedding Dimensions

- **OpenAI text-embedding-3-small:** 1536 dimensions
- **OpenAI text-embedding-3-large:** 3072 dimensions
- **Cohere embed-english-v3.0:** 1024 dimensions

**Important:** Adjust the vector dimension in `document_chunk.embedding` column and all functions if using a different embedding model.

To change dimensions, update:
```sql
ALTER TABLE main.document_chunk 
ALTER COLUMN embedding TYPE vector(3072); -- for larger models
```

## Chunking Strategy

The default chunking strategy splits documents by character count. For better results, consider:
- **Sentence-based chunking:** Split on sentence boundaries
- **Paragraph-based chunking:** Split on paragraph boundaries
- **Semantic chunking:** Use models to identify semantic boundaries
- **Overlap:** 200 characters overlap helps maintain context across chunks

## Performance Optimization

1. **IVFFlat Index:** Already created on `document_chunk.embedding`
   - Adjust `lists` parameter based on data size
   - For < 1M vectors: lists = 100 (default)
   - For 1M-10M vectors: lists = rows / 1000
   - For > 10M vectors: consider HNSW index

2. **Similarity Search Performance:**
   - Use appropriate similarity threshold to reduce results
   - Limit result count to avoid large result sets
   - Filter by project_id for better performance

## Example Usage in n8n

### Complete RAG-Enhanced Agent Prompt Workflow

1. **Get Query Embedding** (HTTP Request to OpenAI)
2. **Search Relevant Documents** (Postgres: `fn_search_documents_rag`)
3. **Build Enhanced Prompt** (Code node)
4. **Send to Agent** (HTTP Request to Cursor API)

This enables the agent to have relevant context from project documents without sending entire documents every time.

