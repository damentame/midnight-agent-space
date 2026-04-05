# Vector Storage Guide

## pgvector Overview

**pgvector** is a PostgreSQL extension that adds vector data type and similarity search capabilities. It enables:

- **Vector Data Type**: Store arrays of floats as a native type
- **Similarity Operators**: `<->` (Euclidean), `<=>` (Cosine), `<#>` (Inner Product)
- **Vector Indexes**: HNSW and IVFFlat for fast similarity search

### Why pgvector?

- **Native Integration**: Works seamlessly with PostgreSQL
- **Performance**: Optimized indexes for similarity search
- **Flexibility**: Multiple distance metrics
- **Mature**: Production-ready, widely used

## Database Schema Design

### document_chunk Table

Stores the actual text chunks:

```sql
CREATE TABLE main.document_chunk (
    chunk_id          BIGSERIAL PRIMARY KEY,
    document_id       BIGINT NOT NULL,
    project_id        BIGINT NOT NULL,
    chunk_index       INT NOT NULL,
    chunk_text        TEXT NOT NULL,
    chunk_metadata    JSONB,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Design Principles**:
- No foreign keys (as per your convention)
- Redundant `project_id` for direct queries
- `chunk_index` maintains document order
- `chunk_metadata` stores flexible JSON data

### document_embedding Table

Stores vector embeddings:

```sql
CREATE TABLE main.document_embedding (
    embedding_id      BIGSERIAL PRIMARY KEY,
    chunk_id          BIGINT NOT NULL,
    document_id       BIGINT NOT NULL,
    project_id        BIGINT NOT NULL,
    embedding         vector(1536) NOT NULL,
    embedding_model   VARCHAR(100) NOT NULL,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Points**:
- `vector(1536)` is the pgvector data type
- Dimension matches OpenAI text-embedding-3-small
- Separate table allows multiple embeddings per chunk (different models)
- Redundant IDs for efficient queries

## Vector Indexing

### HNSW Index

We use **HNSW (Hierarchical Navigable Small World)** index:

```sql
CREATE INDEX idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Parameters**:
- `m = 16`: Number of connections per node (higher = more accurate, slower)
- `ef_construction = 64`: Search width during construction (higher = better quality, slower build)
- `vector_cosine_ops`: Operator class for cosine similarity

### HNSW vs. IVFFlat

| Index Type | Build Speed | Query Speed | Accuracy | Use Case |
|------------|-------------|-------------|----------|----------|
| HNSW | Slower | Fast | High | Production (our choice) |
| IVFFlat | Fast | Medium | Medium | Development/testing |

**Why HNSW?**
- Better query performance
- More accurate results
- Worth the slower build time for production

### Index Parameters

**m (connections per node)**:
- Lower (8-16): Faster queries, less accurate
- Higher (32-64): Slower queries, more accurate
- **Recommended**: 16 for balanced performance

**ef_construction**:
- Lower (40-64): Faster build, lower quality
- Higher (128-200): Slower build, higher quality
- **Recommended**: 64 for good balance

## Step-by-Step: How to Store Vectors

### Step 1: Insert Chunks into document_chunk Table

```python
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO main.document_chunk 
            (document_id, project_id, chunk_index, chunk_text, chunk_metadata)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING chunk_id
        """, (document_id, project_id, chunk_index, chunk_text, metadata_json))
        chunk_id = cur.fetchone()[0]
```

### Step 2: Get chunk_ids from Inserts

The `RETURNING` clause gives us the `chunk_id` immediately after insert.

### Step 3: Insert Embeddings into document_embedding Table

```python
# Convert embedding list to PostgreSQL array format
embedding_str = "[" + ",".join(map(str, embedding)) + "]"

cur.execute("""
    INSERT INTO main.document_embedding
    (chunk_id, document_id, project_id, embedding, embedding_model)
    VALUES (%s, %s, %s, %s::vector, %s)
""", (chunk_id, document_id, project_id, embedding_str, model_name))
```

**Important**: Embeddings must be converted to string format for PostgreSQL.

### Step 4: Create Vector Index (if needed)

```sql
-- Only needed once, or when rebuilding
CREATE INDEX IF NOT EXISTS idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### Step 5: Verify Data Integrity

```sql
-- Check chunk count
SELECT COUNT(*) FROM main.document_chunk WHERE document_id = 45;

-- Check embedding count (should match)
SELECT COUNT(*) FROM main.document_embedding WHERE document_id = 45;

-- Verify dimensions
SELECT 
    embedding_id,
    array_length(embedding::float[], 1) as dimensions
FROM main.document_embedding
WHERE array_length(embedding::float[], 1) != 1536;
```

## Code Walkthrough

### Location: `temporal/activities/document_activities.py`

**Key Function: `store_vectors_activity()`**

```python
@activity.defn
async def store_vectors_activity(chunks_with_embeddings: List[Dict[str, Any]]) -> List[int]:
    chunk_ids = []
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            for chunk in chunks_with_embeddings:
                # Insert chunk
                cur.execute("INSERT INTO main.document_chunk ... RETURNING chunk_id")
                chunk_id = cur.fetchone()[0]
                chunk_ids.append(chunk_id)
                
                # Insert embedding
                embedding = chunk.get("embedding")
                if embedding:
                    cur.execute("INSERT INTO main.document_embedding ...")
            
            conn.commit()
    
    return chunk_ids
```

## Index Maintenance

### When to Rebuild Indexes

- After bulk inserts (better performance)
- When query performance degrades
- After significant data changes

### Rebuilding an Index

```sql
DROP INDEX IF EXISTS main.idx_document_embedding_vector_hnsw;

CREATE INDEX idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Note**: Rebuilding can take time for large datasets.

## Performance Considerations

### Query Performance

- **With Index**: Fast similarity search (milliseconds)
- **Without Index**: Full table scan (seconds to minutes)

### Storage Size

- **Per Embedding**: ~6KB (1536 floats × 4 bytes)
- **1M Embeddings**: ~6GB storage
- **Index Overhead**: ~20-30% additional space

### Best Practices

1. **Batch Inserts**: Insert multiple rows in one transaction
2. **Index After Bulk Load**: Create index after inserting all data
3. **Monitor Size**: Track table and index sizes
4. **Vacuum Regularly**: Keep PostgreSQL statistics updated

## Troubleshooting

**Problem**: Index creation fails
- **Solution**: Ensure pgvector extension is installed: `CREATE EXTENSION vector;`

**Problem**: Slow similarity searches
- **Solution**: Verify index exists, consider rebuilding with higher `m`

**Problem**: Dimension errors
- **Solution**: Check embedding dimension matches `vector(1536)` type

**Problem**: Storage growing too fast
- **Solution**: Consider archiving old embeddings, use partitioning

## Next Steps

- Learn about [Similarity Search](04_SIMILARITY_SEARCH_GUIDE.md)
- See the [Complete Workflow](05_RAG_WORKFLOW_GUIDE.md)
- Check [Examples](07_EXAMPLES.md) for code samples

