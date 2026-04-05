# Similarity Search Guide

## Vector Similarity Search Concepts

Vector similarity search finds documents by **meaning**, not keywords. It works by:

1. Converting query text to an embedding vector
2. Comparing query vector to stored vectors
3. Ranking results by similarity (distance)

## Distance Metrics

pgvector supports three distance operators:

### 1. Cosine Distance (`<=>`)

**Best for**: General semantic similarity

```sql
SELECT * FROM document_embedding
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 10;
```

**Characteristics**:
- Normalized (0 to 2)
- 0 = identical, 2 = opposite
- **Recommended for most use cases**

### 2. Euclidean Distance (`<->`)

**Best for**: When magnitude matters

```sql
SELECT * FROM document_embedding
ORDER BY embedding <-> '[0.1, 0.2, ...]'::vector
LIMIT 10;
```

**Characteristics**:
- Measures straight-line distance
- Not normalized
- Useful for exact matches

### 3. Inner Product (`<#>`)

**Best for**: When direction matters more than magnitude

```sql
SELECT * FROM document_embedding
ORDER BY embedding <#> '[0.1, 0.2, ...]'::vector
LIMIT 10;
```

**Characteristics**:
- Negative values (closer to 0 = more similar)
- Less commonly used

## Query Patterns

### Basic Similarity Search

```python
from utils.vector_utils import search_similar_chunks

results = search_similar_chunks(
    query_text="Python programming",
    project_id=1,
    limit=10,
    distance_metric="cosine"
)
```

### With Similarity Threshold

```python
results = search_similar_chunks(
    query_text="Python programming",
    project_id=1,
    limit=10,
    similarity_threshold=0.3,  # Max distance
    distance_metric="cosine"
)
```

### Filtered Search

```python
# Search within specific document
results = search_similar_chunks(
    query_text="API design",
    document_id=45,
    limit=5
)
```

## Top-K Retrieval

**Top-K** means retrieving the K most similar chunks:

```python
# Get top 10 most similar chunks
results = search_similar_chunks(
    query_text="user authentication",
    limit=10  # K = 10
)
```

**Result Format**:
```python
[
    {
        "chunk_id": 123,
        "chunk_text": "User authentication uses JWT tokens...",
        "distance": 0.15,  # Lower = more similar
        "document_id": 45,
        "project_id": 1
    },
    # ... 9 more results
]
```

## Threshold-Based Filtering

Filter results by minimum similarity:

```python
# Only return chunks with distance < 0.3
results = search_similar_chunks(
    query_text="database schema",
    similarity_threshold=0.3,
    distance_metric="cosine"
)
```

**When to Use**:
- Quality control (reject poor matches)
- Performance (fewer results to process)
- Relevance filtering

## Hybrid Search

Combine vector search with metadata filters:

```sql
SELECT 
    dc.chunk_id,
    dc.chunk_text,
    de.embedding <=> $1::vector AS distance
FROM main.document_chunk dc
INNER JOIN main.document_embedding de ON dc.chunk_id = de.chunk_id
WHERE 
    dc.project_id = $2
    AND dc.document_type = 'requirements'  -- Metadata filter
    AND de.embedding <=> $1::vector < 0.3  -- Similarity threshold
ORDER BY distance
LIMIT 10;
```

**Benefits**:
- Vector similarity for relevance
- Metadata filters for precision
- Best of both worlds

## Performance Optimization

### Index Usage

Ensure index is used:

```sql
EXPLAIN ANALYZE
SELECT * FROM main.document_embedding
ORDER BY embedding <=> '[0.1, ...]'::vector
LIMIT 10;
```

Look for:
- `Index Scan using idx_document_embedding_vector_hnsw`
- Fast execution time (< 100ms)

### Query Planning

PostgreSQL query planner automatically uses HNSW index when:
- Distance operator is used (`<=>`, `<->`, `<#>`)
- `ORDER BY` distance
- Index exists on embedding column

### Batch Similarity Searches

For multiple queries, batch them:

```python
queries = ["Python", "Database", "API"]
results = []

for query in queries:
    embedding = generate_embedding(query)
    # Use same embedding for multiple searches
    results.append(search_similar_chunks(...))
```

## Step-by-Step: How to Search Similar Chunks

### Step 1: Generate Embedding for Query Text

```python
from utils.embeddings import generate_embedding

query_text = "How to implement user authentication?"
query_embedding = generate_embedding(query_text)
```

### Step 2: Build SQL Query with Distance Operator

```python
from utils.vector_utils import search_similar_chunks

results = search_similar_chunks(
    query_text=query_text,  # Function generates embedding internally
    project_id=1,
    limit=10,
    distance_metric="cosine"
)
```

**Internal SQL** (simplified):
```sql
SELECT 
    dc.*,
    de.embedding <=> $1::vector AS distance
FROM main.document_chunk dc
JOIN main.document_embedding de ON dc.chunk_id = de.chunk_id
WHERE dc.project_id = $2
ORDER BY distance ASC
LIMIT 10;
```

### Step 3: Execute with LIMIT and ORDER BY

The function handles:
- Query execution
- Distance calculation
- Result ranking
- Threshold filtering

### Step 4: Return Ranked Results with Metadata

```python
for result in results:
    print(f"Distance: {result['distance']}")
    print(f"Text: {result['chunk_text'][:100]}...")
    print(f"Document: {result['document_id']}")
```

## Code Walkthrough

### Location: `temporal/utils/vector_utils.py`

**Key Function: `search_similar_chunks()`**

```python
def search_similar_chunks(
    query_text: str,
    project_id: Optional[int] = None,
    document_id: Optional[int] = None,
    limit: int = 10,
    similarity_threshold: Optional[float] = None,
    distance_metric: str = "cosine"
) -> List[Dict[str, Any]]:
    # 1. Generate query embedding
    query_embedding = generate_embedding(query_text)
    
    # 2. Build WHERE clause with filters
    where_clauses = []
    if project_id:
        where_clauses.append(f"de.project_id = ${param_idx}")
    
    # 3. Choose distance operator
    if distance_metric == "cosine":
        distance_op = "<=>"
    
    # 4. Build and execute query
    query = f"""
        SELECT ... de.embedding {distance_op} $1::vector AS distance
        WHERE {where_sql}
        ORDER BY distance ASC
        LIMIT {limit}
    """
    
    # 5. Apply threshold and return
    return results
```

## Use Cases

### 1. Agent Context Retrieval

When an agent needs context for a task:

```python
relevant_chunks = search_similar_chunks(
    query_text=task_description,
    project_id=project_id,
    limit=5
)

# Assemble context
context = "\n\n".join([chunk["chunk_text"] for chunk in relevant_chunks])
```

### 2. Requirement Discovery

Find related requirements:

```python
requirements = search_similar_chunks(
    query_text="user authentication requirements",
    document_type="requirements",
    limit=10
)
```

### 3. Code Reference Finding

Find relevant code examples:

```python
code_chunks = search_similar_chunks(
    query_text="REST API implementation",
    document_type="code",
    limit=5
)
```

## Best Practices

1. **Distance Metric**: Use cosine for most cases
2. **Limit Results**: Always use LIMIT (10-50 is typical)
3. **Thresholds**: Set thresholds to filter low-quality matches
4. **Metadata Filters**: Combine with document_type, project_id filters
5. **Index Maintenance**: Rebuild index periodically for performance

## Troubleshooting

**Problem**: Slow queries
- **Solution**: Verify index exists, check EXPLAIN ANALYZE

**Problem**: Poor results
- **Solution**: Check embedding quality, adjust threshold

**Problem**: No results
- **Solution**: Verify embeddings exist, check query embedding generation

**Problem**: Wrong distance values
- **Solution**: Verify distance metric matches use case

## Next Steps

- See the [Complete RAG Workflow](05_RAG_WORKFLOW_GUIDE.md)
- Check [Examples](07_EXAMPLES.md) for code samples
- Review [Troubleshooting Guide](06_TROUBLESHOOTING.md)

