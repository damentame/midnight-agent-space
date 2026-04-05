# Troubleshooting Guide

## Common Issues and Solutions

### Chunking Issues

#### Problem: Empty Chunks

**Symptoms**: Chunks array is empty after chunking

**Causes**:
- Document has no text content
- Text extraction failed
- Encoding issues

**Solutions**:
```python
# Check document content
text = extract_document_content(document)
if not text or not text.strip():
    logger.warning(f"Empty content for document {document_id}")
    return []

# Verify encoding
try:
    text = file_content.decode("utf-8")
except UnicodeDecodeError:
    # Try other encodings
    text = file_content.decode("latin-1")
```

#### Problem: Chunks Split in Middle of Sentences

**Symptoms**: Chunks break mid-sentence

**Causes**:
- Separator priority incorrect
- Chunk size too small
- Missing sentence separators

**Solutions**:
```python
# Ensure sentence separator is included
separators = ["\n\n", "\n", ". ", " ", ""]  # .  is important!

# Increase chunk size if too small
chunk_size = 1500  # Instead of 500
```

#### Problem: Too Many/Few Chunks

**Symptoms**: Document produces unexpected number of chunks

**Causes**:
- Chunk size inappropriate for document
- Overlap too large/small

**Solutions**:
```python
# Adjust chunk size based on document type
if document_type == "code":
    chunk_size = 2000  # Code can handle larger chunks
elif document_type == "requirements":
    chunk_size = 800   # Requirements benefit from smaller chunks

# Adjust overlap
chunk_overlap = int(chunk_size * 0.2)  # 20% overlap
```

### Embedding Issues

#### Problem: Rate Limit Errors

**Symptoms**: `RateLimitError` from OpenAI API

**Causes**:
- Too many requests
- Batch size too large
- No retry logic

**Solutions**:
```python
# Reduce batch size
batch_size = 50  # Instead of 200

# Increase retry delay
retry_delay = 2.0  # Wait longer between retries

# Implement exponential backoff
wait_time = retry_delay * (2 ** retry_count)
```

#### Problem: Embedding Dimension Mismatch

**Symptoms**: Error when storing embeddings, dimension != 1536

**Causes**:
- Wrong model used
- API returned wrong dimensions
- Data corruption

**Solutions**:
```python
# Validate dimensions
expected_dim = 1536
if len(embedding) != expected_dim:
    raise ValueError(f"Dimension mismatch: {len(embedding)} != {expected_dim}")

# Verify model
model = "text-embedding-3-small"  # Not "text-embedding-ada-002"
```

#### Problem: Slow Embedding Generation

**Symptoms**: Embeddings take too long to generate

**Causes**:
- Batch size too small
- Sequential processing
- Network latency

**Solutions**:
```python
# Increase batch size (within API limits)
batch_size = 100  # Optimal for most cases

# Process in parallel (if multiple documents)
import asyncio
tasks = [generate_embeddings_batch(chunks) for chunks in all_chunks]
results = await asyncio.gather(*tasks)
```

### Vector Storage Issues

#### Problem: Index Creation Fails

**Symptoms**: `ERROR: extension "vector" does not exist`

**Causes**:
- pgvector extension not installed
- Wrong database
- Permissions issue

**Solutions**:
```sql
-- Install extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';
```

#### Problem: Slow Similarity Searches

**Symptoms**: Queries take seconds instead of milliseconds

**Causes**:
- Index missing
- Index not used by query planner
- Index parameters suboptimal

**Solutions**:
```sql
-- Verify index exists
SELECT indexname FROM pg_indexes 
WHERE tablename = 'document_embedding';

-- Check query plan
EXPLAIN ANALYZE
SELECT * FROM main.document_embedding
ORDER BY embedding <=> '[0.1, ...]'::vector
LIMIT 10;

-- Rebuild index with better parameters
DROP INDEX idx_document_embedding_vector_hnsw;
CREATE INDEX idx_document_embedding_vector_hnsw 
    ON main.document_embedding 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 32, ef_construction = 128);  -- Higher quality
```

#### Problem: Storage Growing Too Fast

**Symptoms**: Database size increasing rapidly

**Causes**:
- Too many chunks per document
- Embeddings not cleaned up
- No archiving strategy

**Solutions**:
```sql
-- Archive old embeddings
DELETE FROM main.document_embedding
WHERE created_at < NOW() - INTERVAL '1 year';

-- Monitor chunk counts
SELECT 
    document_id,
    COUNT(*) as chunk_count
FROM main.document_chunk
GROUP BY document_id
ORDER BY chunk_count DESC;
```

### Search Issues

#### Problem: No Results from Search

**Symptoms**: `search_similar_chunks()` returns empty list

**Causes**:
- No embeddings in database
- Query embedding generation failed
- Dimension mismatch

**Solutions**:
```python
# Verify embeddings exist
from utils.db import execute_query

results = execute_query("""
    SELECT COUNT(*) as count 
    FROM main.document_embedding 
    WHERE project_id = %s
""", (project_id,))

print(f"Embeddings in database: {results[0]['count']}")

# Test query embedding
query_embedding = generate_embedding("test query")
print(f"Query embedding dimension: {len(query_embedding)}")
```

#### Problem: Poor Search Results

**Symptoms**: Retrieved chunks not relevant to query

**Causes**:
- Embedding quality issues
- Wrong distance metric
- Threshold too high/low

**Solutions**:
```python
# Try different distance metrics
results_cosine = search_similar_chunks(query, distance_metric="cosine")
results_euclidean = search_similar_chunks(query, distance_metric="euclidean")

# Adjust threshold
results = search_similar_chunks(
    query,
    similarity_threshold=0.2,  # Stricter (lower distance)
    limit=10
)

# Check embedding quality
# Poor embeddings = poor results
```

## Debugging Techniques

### How to Inspect Chunks

```python
# Get chunks for a document
from utils.db import execute_query

chunks = execute_query("""
    SELECT 
        chunk_id,
        chunk_index,
        LEFT(chunk_text, 100) as preview,
        chunk_metadata
    FROM main.document_chunk
    WHERE document_id = %s
    ORDER BY chunk_index
""", (document_id,))

for chunk in chunks:
    print(f"Chunk {chunk['chunk_index']}: {chunk['preview']}...")
```

### How to Verify Embeddings

```python
# Check embedding dimensions
from utils.db import execute_query

embeddings = execute_query("""
    SELECT 
        embedding_id,
        chunk_id,
        array_length(embedding::float[], 1) as dims,
        embedding_model
    FROM main.document_embedding
    WHERE document_id = %s
    LIMIT 10
""", (document_id,))

for emb in embeddings:
    print(f"Embedding {emb['embedding_id']}: {emb['dims']} dimensions")
    assert emb['dims'] == 1536, "Dimension mismatch!"
```

### How to Test Similarity Search

```python
# Simple test query
from utils.vector_utils import search_similar_chunks

results = search_similar_chunks(
    query_text="test query",
    project_id=1,
    limit=5
)

print(f"Found {len(results)} results")
for result in results:
    print(f"Distance: {result['distance']:.4f}")
    print(f"Text: {result['chunk_text'][:100]}...")
```

### Performance Profiling

```python
import time

# Profile embedding generation
start = time.time()
embeddings = generate_embeddings_batch(texts)
duration = time.time() - start
print(f"Generated {len(embeddings)} embeddings in {duration:.2f}s")
print(f"Average: {duration/len(embeddings)*1000:.2f}ms per embedding")

# Profile search
start = time.time()
results = search_similar_chunks(query, limit=10)
duration = time.time() - start
print(f"Search took {duration*1000:.2f}ms")
```

## Best Practices

### Optimal Chunk Sizes

| Document Type | Recommended Chunk Size | Overlap |
|---------------|----------------------|---------|
| Code | 1500-2000 | 200-300 |
| Requirements | 800-1200 | 150-200 |
| Documentation | 1000-1500 | 200 |
| Prose/Articles | 1000 | 200 |

### Embedding Batch Sizes

- **Small projects** (< 100 docs): 50-100 per batch
- **Medium projects** (100-1000 docs): 100-200 per batch
- **Large projects** (> 1000 docs): 200 per batch (max API limit)

### When to Regenerate Embeddings

Regenerate if:
- Embedding model changed
- Chunking strategy changed significantly
- Data quality issues discovered
- Model updates available

**Don't regenerate if**:
- Only adding new documents (just embed new ones)
- Minor chunking parameter tweaks
- Performance is acceptable

### Index Maintenance

**Rebuild index when**:
- After bulk inserts (> 10K embeddings)
- Query performance degrades
- Index size > 50% of table size
- After significant data changes

**Schedule**:
- Weekly for active systems
- After major data imports
- When performance monitoring indicates need

## Getting Help

### Check Logs

All components log errors and warnings:
- Temporal workflow logs
- Activity execution logs
- Database query logs

### Verify Configuration

```python
from config import config

print(f"Database: {config.database.connection_string}")
print(f"OpenAI Model: {config.openai.embedding_model}")
print(f"Chunk Size: {config.chunking.chunk_size}")
```

### Test Components Individually

```python
# Test chunking
chunks = chunk_document("Test document text...", 1, 1)
assert len(chunks) > 0

# Test embedding
embedding = generate_embedding("Test text")
assert len(embedding) == 1536

# Test storage
chunk_ids = await store_vectors_activity(chunks_with_embeddings)
assert len(chunk_ids) == len(chunks)
```

## Next Steps

- Review [Examples](07_EXAMPLES.md) for working code
- Check component-specific guides for detailed help
- Verify your configuration matches examples

