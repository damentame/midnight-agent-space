# Document Chunking Guide

## What is Document Chunking?

Document chunking is the process of splitting large documents into smaller, manageable pieces called "chunks". This is essential for RAG because:

- **LLM Context Limits**: Most LLMs have token limits (e.g., 4K, 8K, 32K tokens). Large documents exceed these limits.
- **Precision**: Smaller chunks allow more precise retrieval of relevant information.
- **Efficiency**: Processing smaller chunks is faster and more cost-effective.

## Why Semantic Chunking?

We use **semantic chunking** rather than fixed-size splitting because:

- **Preserves Meaning**: Chunks respect sentence and paragraph boundaries
- **Better Context**: Each chunk is a complete thought or concept
- **Improved Retrieval**: Semantic chunks are more likely to be relevant when retrieved

## Implementation: RecursiveCharacterTextSplitter

Our implementation uses LangChain's `RecursiveCharacterTextSplitter`, which:

1. Tries to split on large separators first (paragraphs, then sentences)
2. Falls back to smaller separators if chunks are still too large
3. Maintains overlap between chunks to preserve context

### How It Works

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,        # Maximum characters per chunk
    chunk_overlap=200,      # Overlap between chunks
    separators=["\n\n", "\n", ". ", " ", ""]  # Splitting priority
)

chunks = splitter.split_text(document_text)
```

### Separator Priority

The splitter tries separators in order:
1. `\n\n` - Double newlines (paragraphs)
2. `\n` - Single newlines
3. `. ` - Sentence endings
4. ` ` - Spaces
5. `""` - Character-by-character (last resort)

## Chunk Metadata

Each chunk includes metadata for retrieval and context:

```python
{
    "chunk_id": 123,
    "document_id": 45,
    "project_id": 1,
    "chunk_index": 2,  # Order within document (0-based)
    "chunk_text": "The actual chunk content...",
    "chunk_metadata": {
        "start_pos": 1500,      # Character position in original document
        "end_pos": 2500,
        "chunk_size": 1000,     # Character count
        "token_count": 250,     # Estimated tokens
        "chunk_index": 2
    }
}
```

### Why Metadata Matters

- **Position Tracking**: Know where chunk came from in original document
- **Token Counting**: Estimate LLM usage
- **Ordering**: Maintain document structure
- **Debugging**: Trace chunks back to source

## Step-by-Step: How to Chunk a Document

### Step 1: Extract Text Content

```python
from utils.chunking import extract_document_content

document = {
    "document_id": 45,
    "raw_text_content": "Your document text here...",
    # or "file_content": bytes(...)
}

text_content = extract_document_content(document)
```

The function prioritizes:
1. `raw_text_content` (if available)
2. `file_content` (decoded from bytes)
3. `structured_json` (if contains text fields)

### Step 2: Initialize Text Splitter

```python
from utils.chunking import chunk_document
from config import config

# Uses configuration defaults
chunks = chunk_document(
    text=text_content,
    document_id=45,
    project_id=1,
    chunk_size=config.chunking.chunk_size,      # Default: 1000
    chunk_overlap=config.chunking.chunk_overlap, # Default: 200
    separators=config.chunking.chunk_separators
)
```

### Step 3: Split Text into Chunks

The splitter automatically:
- Respects sentence boundaries
- Maintains overlap between chunks
- Handles edge cases (empty text, very short documents)

### Step 4: Generate Metadata

Each chunk gets metadata:
- Position in original document
- Token count (using tiktoken)
- Size information
- Index for ordering

### Step 5: Store Chunks in Database

Chunks are stored via the `store_vectors_activity` which:
- Inserts into `main.document_chunk` table
- Returns `chunk_id` for each chunk
- Prepares chunks for embedding generation

## Code Walkthrough

### Location: `temporal/utils/chunking.py`

**Key Function: `chunk_document()`**

```python
def chunk_document(
    text: str,
    document_id: int,
    project_id: int,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    separators: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    # 1. Initialize splitter with parameters
    text_splitter = RecursiveCharacterTextSplitter(...)
    
    # 2. Split text
    chunks = text_splitter.split_text(text)
    
    # 3. Build metadata for each chunk
    for index, chunk_text in enumerate(chunks):
        # Find position, count tokens, build metadata
        ...
    
    return chunk_objects
```

## Configuration

Chunking behavior is controlled by environment variables:

```env
CHUNK_SIZE=1000          # Characters per chunk
CHUNK_OVERLAP=200       # Overlap between chunks
CHUNK_SEPARATORS=["\n\n", "\n", ". ", " ", ""]
```

## Best Practices

1. **Chunk Size**: 
   - Too small: Loses context, too many chunks
   - Too large: Exceeds LLM limits, less precise
   - **Recommended**: 500-1500 characters

2. **Overlap**:
   - Prevents losing context at boundaries
   - **Recommended**: 10-20% of chunk size

3. **Separators**:
   - Match your document structure
   - Code: Use language-specific separators
   - Prose: Use paragraph/sentence separators

## Troubleshooting

**Problem**: Chunks are too small/large
- **Solution**: Adjust `CHUNK_SIZE` in configuration

**Problem**: Losing context at boundaries
- **Solution**: Increase `CHUNK_OVERLAP`

**Problem**: Chunks split in middle of sentences
- **Solution**: Check separator priority, ensure `. ` is included

**Problem**: Empty chunks
- **Solution**: Filter empty chunks before processing

## Next Steps

- Learn about [Embedding Generation](02_EMBEDDINGS_GUIDE.md)
- See [Vector Storage](03_VECTOR_STORAGE_GUIDE.md)
- Check [Examples](07_EXAMPLES.md) for code samples

