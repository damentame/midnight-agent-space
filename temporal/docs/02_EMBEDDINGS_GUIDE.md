# Embeddings Guide

## What are Embeddings?

Embeddings are numerical representations of text that capture semantic meaning. They convert text into vectors (arrays of numbers) where:

- **Similar texts** have **similar vectors**
- **Different texts** have **different vectors**
- **Distance between vectors** represents **semantic similarity**

### Example

```
"Python programming" → [0.1, 0.3, -0.2, ..., 0.5]  (1536 numbers)
"Code in Python"    → [0.12, 0.28, -0.19, ..., 0.48] (very similar!)
"Baking a cake"     → [-0.3, 0.1, 0.4, ..., -0.2]   (very different!)
```

## Why Embeddings Enable Semantic Search

Traditional keyword search finds exact matches:
- Query: "Python code"
- Matches: Documents containing "Python" AND "code"

Vector similarity search finds meaning:
- Query: "Python code"
- Matches: Documents about "programming in Python", "writing Python scripts", etc.

## OpenAI Embedding Models

We use **text-embedding-3-small** which provides:

- **Dimensions**: 1536 (compact but effective)
- **Cost**: Lower than larger models
- **Performance**: Excellent for most use cases
- **Speed**: Fast generation

### Model Comparison

| Model | Dimensions | Cost | Use Case |
|-------|-----------|------|----------|
| text-embedding-3-small | 1536 | Low | General purpose (our choice) |
| text-embedding-3-large | 3072 | Higher | More complex semantics |
| text-embedding-ada-002 | 1536 | Low | Legacy (deprecated) |

## Embedding Generation Process

### How OpenAI API Works

1. **Input**: Text string (up to 8K tokens)
2. **Processing**: Neural network converts text to vector
3. **Output**: Array of 1536 floating-point numbers

### API Call Example

```python
from openai import OpenAI

client = OpenAI(api_key="your-key")
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="Your text here"
)
embedding = response.data[0].embedding  # List of 1536 floats
```

## Batch Processing

For efficiency, we process multiple texts in batches:

```python
# Single call for multiple texts
response = client.embeddings.create(
    model="text-embedding-3-small",
    input=["Text 1", "Text 2", "Text 3", ...]  # Up to 2048 texts
)
```

### Benefits

- **Faster**: One API call vs. many
- **Cost-effective**: Same pricing, less overhead
- **Rate limit friendly**: Fewer requests

## Dimension Considerations

### Why 1536 Dimensions?

- **Balance**: Enough information, not too large
- **Storage**: ~6KB per embedding (1536 × 4 bytes)
- **Performance**: Fast similarity calculations
- **Quality**: Captures semantic relationships well

### Validation

Always validate embedding dimensions:

```python
expected_dim = 1536
if len(embedding) != expected_dim:
    raise ValueError(f"Dimension mismatch: {len(embedding)} != {expected_dim}")
```

## Error Handling & Retries

### Rate Limiting

OpenAI has rate limits. We handle this with:

1. **Exponential Backoff**: Wait longer between retries
2. **Retry Logic**: Attempt multiple times
3. **Batch Sizing**: Process in manageable batches

```python
# Retry with exponential backoff
retries = 0
max_retries = 3
while retries <= max_retries:
    try:
        response = client.embeddings.create(...)
        break
    except RateLimitError:
        wait_time = retry_delay * (2 ** retries)  # 1s, 2s, 4s
        time.sleep(wait_time)
        retries += 1
```

### Common Errors

- **RateLimitError**: Too many requests → Wait and retry
- **InvalidRequestError**: Text too long → Split text
- **APIError**: Service issue → Retry with backoff

## Step-by-Step: How to Generate Embeddings

### Step 1: Prepare Chunks for Embedding

```python
chunks = [
    {"chunk_text": "First chunk text..."},
    {"chunk_text": "Second chunk text..."},
    # ...
]

texts = [chunk["chunk_text"] for chunk in chunks]
```

### Step 2: Initialize OpenAI Client

```python
from utils.embeddings import get_client

client = get_client()  # Uses config.openai.api_key
```

### Step 3: Batch Chunks for API Calls

```python
batch_size = 100  # From config
for i in range(0, len(texts), batch_size):
    batch = texts[i:i + batch_size]
    # Process batch...
```

### Step 4: Generate Embeddings with Retry Logic

```python
from utils.embeddings import generate_embeddings_batch

embeddings = generate_embeddings_batch(
    texts=texts,
    model="text-embedding-3-small",
    batch_size=100,
    max_retries=3,
    retry_delay=1.0
)
```

### Step 5: Validate Embedding Dimensions

```python
from utils.embeddings import validate_embedding_dimension

for embedding in embeddings:
    if not validate_embedding_dimension(embedding):
        raise ValueError("Invalid embedding dimension")
```

### Step 6: Return Embeddings with Chunk Associations

```python
chunks_with_embeddings = []
for chunk, embedding in zip(chunks, embeddings):
    chunk["embedding"] = embedding
    chunks_with_embeddings.append(chunk)
```

## Code Walkthrough

### Location: `temporal/utils/embeddings.py`

**Key Function: `generate_embeddings_batch()`**

```python
def generate_embeddings_batch(
    texts: List[str],
    model: Optional[str] = None,
    batch_size: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[float] = None
) -> List[List[float]]:
    # 1. Initialize client
    client = get_client()
    
    # 2. Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        # 3. Retry logic
        retries = 0
        while retries <= max_retries:
            try:
                response = client.embeddings.create(...)
                # Success!
                break
            except RateLimitError:
                # Wait and retry
                ...
```

## Configuration

Embedding behavior is controlled by:

```env
OPENAI_API_KEY=your_key_here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
EMBEDDING_BATCH_SIZE=100
EMBEDDING_MAX_RETRIES=3
EMBEDDING_RETRY_DELAY=1.0
```

## Best Practices

1. **Batch Size**: 
   - Too small: Many API calls, slower
   - Too large: Rate limit issues
   - **Recommended**: 50-200 texts per batch

2. **Retry Strategy**:
   - Exponential backoff prevents overwhelming API
   - Max 3-5 retries to avoid infinite loops

3. **Error Handling**:
   - Log all errors for debugging
   - Don't fail entire batch for one error
   - Validate dimensions after generation

4. **Cost Management**:
   - Batch processing reduces API calls
   - Cache embeddings when possible
   - Monitor usage via OpenAI dashboard

## Troubleshooting

**Problem**: Rate limit errors
- **Solution**: Reduce batch size, increase retry delay

**Problem**: Dimension mismatches
- **Solution**: Check model name, validate after generation

**Problem**: Slow embedding generation
- **Solution**: Increase batch size (within limits), use async

**Problem**: API key errors
- **Solution**: Verify `OPENAI_API_KEY` in environment

## Next Steps

- Learn about [Vector Storage](03_VECTOR_STORAGE_GUIDE.md)
- Explore [Similarity Search](04_SIMILARITY_SEARCH_GUIDE.md)
- See [Examples](07_EXAMPLES.md) for code samples

