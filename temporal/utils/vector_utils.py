"""Vector similarity search and utility functions."""
from typing import List, Dict, Any, Optional
import logging
from functools import lru_cache
import hashlib
import json

from temporal.utils.db import execute_query
from temporal.utils.embeddings import generate_embedding
from temporal.config import config

logger = logging.getLogger(__name__)

# Cache for query embeddings (same query = same embedding)
_embedding_cache: Dict[str, List[float]] = {}

# Cache for RAG results (keyed by query hash + project_id)
_rag_result_cache: Dict[str, Dict[str, Any]] = {}


def validate_embedding_dimension(embedding: List[float]) -> bool:
    """Validate that embedding has the correct dimension."""
    expected_dim = config.openai.embedding_dimensions
    actual_dim = len(embedding)
    
    if actual_dim != expected_dim:
        logger.error(
            f"Embedding dimension mismatch: expected {expected_dim}, got {actual_dim}"
        )
        return False
    return True


def _get_cached_embedding(query_text: str) -> List[float]:
    """Get cached embedding or generate and cache it."""
    # Use hash of query text as cache key
    query_hash = hashlib.md5(query_text.encode()).hexdigest()
    
    if query_hash not in _embedding_cache:
        _embedding_cache[query_hash] = generate_embedding(query_text)
        logger.debug(f"Cached embedding for query: {query_text[:50]}...")
    
    return _embedding_cache[query_hash]


def _get_rag_cache_key(query_text: str, project_id: int, limit: int, similarity_threshold: float) -> str:
    """Generate cache key for RAG results."""
    cache_data = {
        "query": query_text,
        "project_id": project_id,
        "limit": limit,
        "similarity_threshold": similarity_threshold
    }
    return hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()


def search_similar_chunks(
    query_text: str,
    project_id: Optional[int] = None,
    document_id: Optional[int] = None,
    limit: int = 10,
    similarity_threshold: Optional[float] = None,
    distance_metric: str = "cosine",
    use_cache: bool = True
) -> List[Dict[str, Any]]:
    """
    Search for similar document chunks using vector similarity.
    
    Args:
        query_text: Text to search for
        project_id: Optional project filter
        document_id: Optional document filter
        limit: Maximum number of results
        similarity_threshold: Optional minimum similarity score
        distance_metric: 'cosine', 'euclidean', or 'inner_product'
        use_cache: Whether to use cached embeddings (default: True)
        
    Returns:
        List of similar chunks with similarity scores
    """
    # Generate embedding for query (with caching)
    if use_cache:
        query_embedding = _get_cached_embedding(query_text)
    else:
        query_embedding = generate_embedding(query_text)
    
    if not validate_embedding_dimension(query_embedding):
        return []
    
    # Convert to PostgreSQL array format
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    # Build WHERE clause
    where_clauses = []
    params = [embedding_str]
    param_idx = 2
    
    if project_id:
        where_clauses.append(f"de.project_id = ${param_idx}")
        params.append(project_id)
        param_idx += 1
    
    if document_id:
        where_clauses.append(f"de.document_id = ${param_idx}")
        params.append(document_id)
        param_idx += 1
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    # Choose distance operator
    if distance_metric == "cosine":
        distance_op = "<=>"
    elif distance_metric == "euclidean":
        distance_op = "<->"
    elif distance_metric == "inner_product":
        distance_op = "<#>"
    else:
        logger.warning(f"Unknown distance metric {distance_metric}, using cosine")
        distance_op = "<=>"
    
    # Build query
    query = f"""
        SELECT 
            dc.chunk_id,
            dc.document_id,
            dc.project_id,
            dc.chunk_index,
            dc.chunk_text,
            dc.chunk_metadata,
            de.embedding_id,
            de.embedding_model,
            de.embedding {distance_op} $1::vector AS distance
        FROM main.document_chunk dc
        INNER JOIN main.document_embedding de ON dc.chunk_id = de.chunk_id
        WHERE {where_sql}
        ORDER BY distance ASC
        LIMIT ${param_idx}
    """
    params.append(limit)
    
    try:
        results = execute_query(query, tuple(params))
        
        # Apply similarity threshold if provided
        if similarity_threshold is not None:
            if distance_metric == "cosine":
                # Cosine distance: lower is more similar, threshold is max distance
                results = [r for r in results if r["distance"] <= similarity_threshold]
            else:
                # For other metrics, threshold logic may differ
                logger.warning(f"Similarity threshold not fully supported for {distance_metric}")
        
        return results
        
    except Exception as e:
        logger.error(f"Vector similarity search failed: {e}")
        return []


def get_chunk_embeddings(chunk_ids: List[int]) -> Dict[int, List[float]]:
    """
    Retrieve embeddings for specific chunk IDs.
    
    Args:
        chunk_ids: List of chunk IDs
        
    Returns:
        Dictionary mapping chunk_id to embedding vector
    """
    if not chunk_ids:
        return {}
    
    placeholders = ",".join(["%s"] * len(chunk_ids))
    query = f"""
        SELECT chunk_id, embedding
        FROM main.document_embedding
        WHERE chunk_id IN ({placeholders})
    """
    
    try:
        results = execute_query(query, tuple(chunk_ids))
        return {row["chunk_id"]: row["embedding"] for row in results}
    except Exception as e:
        logger.error(f"Failed to retrieve chunk embeddings: {e}")
        return {}


def clear_embedding_cache():
    """Clear the embedding cache."""
    global _embedding_cache
    _embedding_cache.clear()
    logger.info("Embedding cache cleared")


def clear_rag_cache():
    """Clear the RAG result cache."""
    global _rag_result_cache
    _rag_result_cache.clear()
    logger.info("RAG result cache cleared")


def get_cache_stats() -> Dict[str, int]:
    """Get cache statistics."""
    return {
        "embedding_cache_size": len(_embedding_cache),
        "rag_cache_size": len(_rag_result_cache)
    }

