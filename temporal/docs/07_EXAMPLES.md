# RAG Implementation Examples

## Example 1: Simple Document Chunking

### Code

```python
from utils.chunking import chunk_document, extract_document_content

# Sample document
document = {
    "document_id": 45,
    "project_id": 1,
    "raw_text_content": """
    This is a sample document about Python programming.
    It contains multiple paragraphs that will be split into chunks.
    
    Each paragraph should be treated as a separate semantic unit.
    The chunking process will maintain context through overlap.
    
    Finally, this is the last paragraph of the document.
    """
}

# Extract text
text = extract_document_content(document)

# Chunk the document
chunks = chunk_document(
    text=text,
    document_id=45,
    project_id=1,
    chunk_size=100,
    chunk_overlap=20
)

# Display results
print(f"Created {len(chunks)} chunks:")
for chunk in chunks:
    print(f"\nChunk {chunk['chunk_index']}:")
    print(f"  Text: {chunk['chunk_text'][:50]}...")
    print(f"  Metadata: {chunk['chunk_metadata']}")
```

### Expected Output

```
Created 3 chunks:

Chunk 0:
  Text: This is a sample document about Python programming...
  Metadata: {'start_pos': 0, 'end_pos': 95, 'chunk_size': 95, 'token_count': 23, 'chunk_index': 0}

Chunk 1:
  Text: It contains multiple paragraphs that will be split...
  Metadata: {'start_pos': 75, 'end_pos': 180, 'chunk_size': 105, 'token_count': 25, 'chunk_index': 1}

Chunk 2:
  Text: Finally, this is the last paragraph of the document...
  Metadata: {'start_pos': 160, 'end_pos': 220, 'chunk_size': 60, 'token_count': 15, 'chunk_index': 2}
```

### Database State After Execution

```sql
SELECT 
    chunk_id,
    chunk_index,
    LEFT(chunk_text, 50) as preview,
    chunk_metadata->>'token_count' as tokens
FROM main.document_chunk
WHERE document_id = 45
ORDER BY chunk_index;
```

## Example 2: Generate and Store Embeddings

### Code

```python
from utils.chunking import chunk_document
from utils.embeddings import add_embeddings_to_chunks
from activities.document_activities import store_vectors_activity

# Step 1: Chunk document
document = {
    "document_id": 45,
    "project_id": 1,
    "raw_text_content": "Your document text here..."
}

chunks = chunk_document(
    text=extract_document_content(document),
    document_id=45,
    project_id=1
)

# Step 2: Generate embeddings
chunks_with_embeddings = add_embeddings_to_chunks(chunks)

# Verify embeddings
for chunk in chunks_with_embeddings:
    assert "embedding" in chunk
    assert len(chunk["embedding"]) == 1536
    print(f"Chunk {chunk['chunk_index']}: embedding generated")

# Step 3: Store in database
chunk_ids = await store_vectors_activity(chunks_with_embeddings)

print(f"Stored {len(chunk_ids)} chunks with embeddings")
print(f"Chunk IDs: {chunk_ids}")
```

### API Call Example

```python
from openai import OpenAI

client = OpenAI(api_key="your-key")

# Single embedding
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="Python programming language"
)
embedding = response.data[0].embedding
print(f"Embedding dimension: {len(embedding)}")  # 1536

# Batch embeddings
response = client.embeddings.create(
    model="text-embedding-3-small",
    input=["Text 1", "Text 2", "Text 3"]
)
print(f"Generated {len(response.data)} embeddings")
```

### Database Queries to Verify

```sql
-- Check chunks stored
SELECT COUNT(*) as chunk_count
FROM main.document_chunk
WHERE document_id = 45;

-- Check embeddings stored
SELECT COUNT(*) as embedding_count
FROM main.document_embedding
WHERE document_id = 45;

-- Verify dimensions
SELECT 
    embedding_id,
    array_length(embedding::float[], 1) as dimensions
FROM main.document_embedding
WHERE document_id = 45
LIMIT 5;

-- All should be 1536
```

## Example 3: Similarity Search Query

### Code

```python
from utils.vector_utils import search_similar_chunks

# Search for relevant chunks
query = "How to implement user authentication?"

results = search_similar_chunks(
    query_text=query,
    project_id=1,
    limit=5,
    distance_metric="cosine"
)

# Display results
print(f"Found {len(results)} relevant chunks:\n")
for i, result in enumerate(results, 1):
    print(f"{i}. Distance: {result['distance']:.4f}")
    print(f"   Document: {result['document_id']}")
    print(f"   Text: {result['chunk_text'][:100]}...")
    print()
```

### Query Construction

The function internally builds this SQL:

```sql
SELECT 
    dc.chunk_id,
    dc.document_id,
    dc.project_id,
    dc.chunk_index,
    dc.chunk_text,
    dc.chunk_metadata,
    de.embedding_id,
    de.embedding_model,
    de.embedding <=> $1::vector AS distance
FROM main.document_chunk dc
INNER JOIN main.document_embedding de ON dc.chunk_id = de.chunk_id
WHERE dc.project_id = $2
ORDER BY distance ASC
LIMIT 5;
```

### Result Interpretation

```python
# Results are ranked by similarity (lower distance = more similar)
for result in results:
    similarity_score = 1 - result["distance"]  # Convert to similarity (0-1)
    
    if similarity_score > 0.8:
        relevance = "Highly relevant"
    elif similarity_score > 0.6:
        relevance = "Relevant"
    else:
        relevance = "Somewhat relevant"
    
    print(f"{relevance} (similarity: {similarity_score:.2f})")
```

### Performance Metrics

```python
import time

start = time.time()
results = search_similar_chunks(query, project_id=1, limit=10)
duration = time.time() - start

print(f"Search completed in {duration*1000:.2f}ms")
print(f"Results per ms: {len(results)/duration/1000:.2f}")
```

## Example 4: Full RAG Pipeline

### Complete End-to-End Example

```python
import asyncio
from workflows.document_serialization_workflow import DocumentSerializationWorkflow
from workflows.document_serialization_workflow import DocumentSerializationInput
from client import start_document_serialization, get_workflow_result

async def full_rag_example():
    """Complete RAG pipeline example."""
    
    # Step 1: Start workflow
    print("Starting document serialization workflow...")
    workflow_id = await start_document_serialization(
        agent_id=2,
        project_id=1,
        use_cursor_api=True
    )
    print(f"Workflow ID: {workflow_id}")
    
    # Step 2: Wait for completion
    print("Waiting for workflow to complete...")
    result = await get_workflow_result(workflow_id)
    
    # Step 3: Display results
    print(f"\nWorkflow Results:")
    print(f"  Project ID: {result.project_id}")
    print(f"  Agent Instance ID: {result.agent_instance_id}")
    print(f"  Documents Processed: {result.documents_processed}")
    print(f"  Total Chunks Created: {result.chunks_created}")
    
    print(f"\nDocument Results:")
    for doc_result in result.serialization_results:
        status_icon = "✓" if doc_result["status"] == "success" else "✗"
        print(f"  {status_icon} Document {doc_result['document_id']}: "
              f"{doc_result.get('chunks_created', 0)} chunks")
    
    # Step 4: Test retrieval
    print("\nTesting similarity search...")
    from utils.vector_utils import search_similar_chunks
    
    test_queries = [
        "user authentication",
        "API endpoints",
        "database schema"
    ]
    
    for query in test_queries:
        results = search_similar_chunks(
            query_text=query,
            project_id=1,
            limit=3
        )
        print(f"\nQuery: '{query}'")
        print(f"  Found {len(results)} relevant chunks")
        for result in results:
            print(f"    - Doc {result['document_id']}: "
                  f"distance={result['distance']:.3f}")

# Run example
if __name__ == "__main__":
    asyncio.run(full_rag_example())
```

### Expected Workflow Execution

```
Starting document serialization workflow...
Workflow ID: document-serialization-1-2

Waiting for workflow to complete...
[Workflow logs show progress...]

Workflow Results:
  Project ID: 1
  Agent Instance ID: 50
  Documents Processed: 3
  Total Chunks Created: 45

Document Results:
  ✓ Document 10: 15 chunks
  ✓ Document 11: 18 chunks
  ✓ Document 12: 12 chunks

Testing similarity search...

Query: 'user authentication'
  Found 3 relevant chunks
    - Doc 10: distance=0.123
    - Doc 11: distance=0.145
    - Doc 10: distance=0.167

Query: 'API endpoints'
  Found 3 relevant chunks
    - Doc 11: distance=0.098
    - Doc 12: distance=0.112
    - Doc 11: distance=0.134

Query: 'database schema'
  Found 3 relevant chunks
    - Doc 12: distance=0.156
    - Doc 10: distance=0.178
    - Doc 12: distance=0.189
```

### Database State After Full Pipeline

```sql
-- Summary of stored data
SELECT 
    'Chunks' as type,
    COUNT(*) as count
FROM main.document_chunk
WHERE project_id = 1

UNION ALL

SELECT 
    'Embeddings' as type,
    COUNT(*) as count
FROM main.document_embedding
WHERE project_id = 1

UNION ALL

SELECT 
    'Documents' as type,
    COUNT(DISTINCT document_id) as count
FROM main.document_chunk
WHERE project_id = 1;

-- Chunks per document
SELECT 
    document_id,
    COUNT(*) as chunk_count,
    AVG((chunk_metadata->>'token_count')::int) as avg_tokens
FROM main.document_chunk
WHERE project_id = 1
GROUP BY document_id
ORDER BY document_id;
```

## Example 5: Using RAG in Agent Context

### Retrieving Context for Task Creation

```python
from utils.vector_utils import search_similar_chunks

def get_agent_context(task_description: str, project_id: int):
    """Get relevant context for an agent task."""
    
    # Search for relevant chunks
    relevant_chunks = search_similar_chunks(
        query_text=task_description,
        project_id=project_id,
        limit=5,
        distance_metric="cosine"
    )
    
    # Build context object
    context = {
        "task": task_description,
        "relevant_sections": [
            {
                "document_id": chunk["document_id"],
                "chunk_index": chunk["chunk_index"],
                "content": chunk["chunk_text"],
                "relevance_score": 1 - chunk["distance"],
                "metadata": chunk.get("chunk_metadata", {})
            }
            for chunk in relevant_chunks
        ],
        "total_sections": len(relevant_chunks)
    }
    
    return context

# Usage
context = get_agent_context(
    "Implement REST API for user management",
    project_id=1
)

print(f"Found {context['total_sections']} relevant sections:")
for section in context["relevant_sections"]:
    print(f"  - Doc {section['document_id']}: "
          f"relevance={section['relevance_score']:.2f}")
```

## Example 6: Batch Processing Multiple Documents

### Efficient Batch Chunking and Embedding

```python
async def process_documents_batch(documents: List[Dict]):
    """Process multiple documents efficiently."""
    
    all_chunks = []
    
    # Step 1: Chunk all documents
    for document in documents:
        chunks = await chunk_document_activity(document)
        all_chunks.extend(chunks)
    
    print(f"Total chunks created: {len(all_chunks)}")
    
    # Step 2: Generate embeddings in batches
    chunks_with_embeddings = await generate_embeddings_activity(all_chunks)
    
    # Step 3: Store all at once
    chunk_ids = await store_vectors_activity(chunks_with_embeddings)
    
    print(f"Stored {len(chunk_ids)} chunks with embeddings")
    return chunk_ids
```

## Next Steps

- Review [Troubleshooting Guide](06_TROUBLESHOOTING.md) if you encounter issues
- Check individual component guides for detailed explanations
- Experiment with different chunk sizes and search parameters

