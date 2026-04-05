# RAG Retrieval Issue - Root Cause and Fix

## Problem Summary

The RAG retrieval was returning **0 chunks** despite having 171 chunks in the database for project 1.

## Root Cause Analysis

### Issue 1: Similarity Threshold Too High
- **Configured threshold**: 0.7 (70% similarity required)
- **Actual similarity scores**: ~0.35 (35% similarity)
- **Result**: No chunks met the threshold, so 0 chunks returned

### Issue 2: Query Text Too Generic
- **Original query**: "Generate tasks for project 1 based on requirements"
- **Document content**: "Terminal-Enabled Notion API Client" requirements
- **Semantic mismatch**: Generic query doesn't match specific document content

### Test Results
```
Testing with similarity threshold: 0.5 → Retrieved 0 chunks
Testing with similarity threshold: 0.6 → Retrieved 0 chunks
Testing with similarity threshold: 0.7 → Retrieved 0 chunks
Testing with similarity threshold: 0.8 → Retrieved 0 chunks

Direct similarity test (top chunk): similarity=0.3451 (34.51%)
```

## Fix Applied

### 1. Lowered Similarity Threshold
- **Changed from**: 0.7 (70%)
- **Changed to**: 0.3 (30%)
- **Location**: 
  - `temporal/workflows/document_serialization_workflow.py` (line 319)
  - `temporal/activities/document_activities.py` (line 259, default parameter)

### 2. Improved Query Text
- **Changed from**: `"Generate tasks for project {project_id} based on requirements"`
- **Changed to**: `"Project requirements and specifications for task generation and implementation"`
- **Reason**: More semantic alignment with document content

### 3. Verification
After fix, with threshold 0.3:
- ✅ **10 chunks retrieved** (as expected)
- ✅ RAG context now available for agent prompts
- ✅ Agent receives relevant document chunks

## Files Modified

1. **temporal/workflows/document_serialization_workflow.py**
   - Line 313: Improved query text
   - Line 319: Lowered threshold from 0.7 to 0.3

2. **temporal/activities/document_activities.py**
   - Line 259: Lowered default threshold from 0.7 to 0.3

## Why This Happened

1. **Embedding Model**: Using `all-MiniLM-L6-v2` (384 dimensions)
   - This model is good but may not capture semantic similarity as well as larger models
   - Generic queries vs. specific document content = lower similarity scores

2. **Cosine Similarity**: 
   - Cosine similarity for semantic search typically ranges 0.3-0.7 for related content
   - 0.7 threshold is appropriate for very similar content (e.g., paraphrases)
   - 0.3 threshold is better for semantically related but different wording

3. **Query-Document Mismatch**:
   - Query: "Generate tasks..." (meta-instruction)
   - Document: "Terminal-Enabled Notion API Client..." (specific requirements)
   - These are semantically related but not identical

## Recommendations

1. **Monitor Similarity Scores**: Log actual similarity scores to tune threshold
2. **Query Optimization**: Use more specific queries that match document terminology
3. **Consider Hybrid Search**: Combine semantic search with keyword matching
4. **Model Upgrade**: Consider larger embedding models (e.g., `text-embedding-3-small`) for better semantic matching

## Testing

To verify the fix works:
```python
# Test with threshold 0.3
python temporal/test_rag_retrieval.py
```

Expected: Should retrieve 10 chunks with similarity scores ~0.3-0.35

