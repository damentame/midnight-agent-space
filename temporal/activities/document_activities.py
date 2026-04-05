"""Document-related Temporal activities."""
import logging
from typing import Dict, Any, List, Optional
import json

from temporalio import activity
from temporal.utils.db import execute_function, execute_query, get_connection
from temporal.utils.activity_run import track_activity
from psycopg2.extras import RealDictCursor
# Lazy import chunking utilities to avoid loading langchain in workflow sandbox
# These are only used in activities, not workflows
# Config import is lazy to avoid file system operations in workflow sandbox

logger = logging.getLogger(__name__)


@activity.defn
@track_activity
async def get_project_documents_activity(project_id: int) -> Dict[str, Any]:
    """
    Get all active documents for a project.
    
    Calls main.fn_get_project_documents() to retrieve documents.
    """
    try:
        logger.info(f"Fetching documents for project {project_id}")
        
        result = execute_function("main.fn_get_project_documents", (project_id,))
        
        if not result:
            return {"project_id": project_id, "documents": [], "document_count": 0}
        
        logger.info(f"Found {result.get('document_count', 0)} documents for project {project_id}")
        return result
        
    except Exception as e:
        import traceback
        logger.error(f"Error fetching project documents: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def chunk_document_activity(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Chunk a document into semantic pieces with enriched metadata.
    
    Extracts text content, fetches project metadata, and splits into chunks.
    """
    # Lazy import to avoid loading langchain in workflow sandbox
    from temporal.utils.chunking import chunk_document, extract_document_content
    
    try:
        document_id = document.get("document_id")
        project_id = document.get("project_id")
        
        logger.info(f"Chunking document {document_id}")
        
        # Extract text content
        text_content = extract_document_content(document)
        
        if not text_content:
            logger.warning(f"No text content found for document {document_id}")
            return []
        
        # Lazy import config to avoid file system operations
        from temporal.config import config
        
        # Prepare document metadata
        document_metadata = {
            "document_name": document.get("document_name"),
            "document_type": document.get("document_type"),
            "version_number": document.get("version_number")
        }
        
        # Fetch project metadata (optional, but enriches chunks)
        project_metadata = None
        try:
            project_query = """
                SELECT project_name, project_type 
                FROM main.project 
                WHERE project_id = %s
                LIMIT 1
            """
            project_result = execute_query(project_query, (project_id,))
            if project_result and len(project_result) > 0:
                project_metadata = {
                    "project_name": project_result[0].get("project_name"),
                    "project_type": project_result[0].get("project_type")
                }
        except Exception as e:
            logger.warning(f"Could not fetch project metadata: {e}, continuing without it")
        
        # Chunk the document with enriched metadata
        chunks = chunk_document(
            text_content,
            document_id,
            project_id,
            chunk_size=config.chunking.chunk_size,
            chunk_overlap=config.chunking.chunk_overlap,
            separators=config.chunking.chunk_separators,
            document_metadata=document_metadata,
            project_metadata=project_metadata
        )
        
        logger.info(f"Document {document_id} chunked into {len(chunks)} pieces")
        return chunks
        
    except Exception as e:
        import traceback
        logger.error(f"Error chunking document: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def generate_embeddings_activity(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate embeddings for document chunks.
    
    Takes chunks and adds embedding vectors to each.
    """
    # Lazy import to avoid loading OpenAI/HTTP libraries in workflow sandbox
    from temporal.utils.embeddings import add_embeddings_to_chunks
    
    try:
        if not chunks:
            return []
        
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        
        # Add embeddings to chunks
        chunks_with_embeddings = add_embeddings_to_chunks(chunks)
        
        logger.info(f"Generated embeddings for {len(chunks_with_embeddings)} chunks")
        return chunks_with_embeddings
        
    except Exception as e:
        import traceback
        logger.error(f"Error generating embeddings: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def store_vectors_activity(chunks_with_embeddings: List[Dict[str, Any]]) -> List[int]:
    """
    Store chunks and embeddings in database.
    
    Inserts into document_chunk and document_embedding tables.
    Returns list of chunk_ids.
    """
    try:
        if not chunks_with_embeddings:
            return []
        
        logger.info(f"Storing {len(chunks_with_embeddings)} chunks and embeddings")
        
        chunk_ids = []
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Insert chunks
                for chunk in chunks_with_embeddings:
                    try:
                        cur.execute("""
                            INSERT INTO main.document_chunk 
                            (document_id, project_id, chunk_index, chunk_text, chunk_metadata)
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING chunk_id
                        """, (
                            chunk["document_id"],
                            chunk["project_id"],
                            chunk["chunk_index"],
                            chunk["chunk_text"],
                            json.dumps(chunk["chunk_metadata"])
                        ))
                        result = cur.fetchone()
                        if result is None:
                            raise ValueError(f"Failed to insert chunk for document {chunk.get('document_id')}: INSERT RETURNING returned None")
                        if not isinstance(result, (tuple, list)) or len(result) == 0:
                            raise ValueError(f"Failed to insert chunk for document {chunk.get('document_id')}: INSERT RETURNING returned invalid result: {result}")
                        chunk_id = result[0]
                        chunk_ids.append(chunk_id)
                    except (IndexError, TypeError) as e:
                        logger.error(f"Error accessing chunk_id from result: {e}")
                        logger.error(f"Result type: {type(result)}, Result value: {result}")
                        logger.error(f"Chunk data: document_id={chunk.get('document_id')}, project_id={chunk.get('project_id')}")
                        raise ValueError(f"Failed to extract chunk_id from INSERT result: {e}") from e
                    
                    # Insert embedding
                    embedding = chunk.get("embedding")
                    if embedding:
                        # Lazy import config to avoid file system operations
                        from temporal.config import config
                        
                        # Convert list to PostgreSQL array format
                        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
                        cur.execute("""
                            INSERT INTO main.document_embedding
                            (chunk_id, document_id, project_id, embedding, embedding_model)
                            VALUES (%s, %s, %s, %s::vector, %s)
                        """, (
                            chunk_id,
                            chunk["document_id"],
                            chunk["project_id"],
                            embedding_str,
                            config.openai.embedding_model
                        ))
                
                conn.commit()
        
        logger.info(f"Stored {len(chunk_ids)} chunks and embeddings")
        return chunk_ids
        
    except Exception as e:
        import traceback
        logger.error(f"Error storing vectors: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


@activity.defn
@track_activity
async def update_document_serialization_activity(
    document_id: int,
    serialized_payload: Dict[str, Any]
) -> None:
    """
    Update document with serialized payload.
    
    Calls main.sp_serialize_document() stored procedure.
    """
    try:
        logger.info(f"Updating document {document_id} with serialization")
        
        # Convert payload to JSONB string
        payload_json = json.dumps(serialized_payload)
        
        # Call stored procedure
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CALL main.sp_serialize_document(%s, %s::jsonb, 'system')
                """, (document_id, payload_json))
                conn.commit()
        
        logger.info(f"Document {document_id} serialization updated")
        
    except Exception as e:
        import traceback
        logger.error(f"Error updating document serialization: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise


async def retrieve_rag_context_impl(
    query_text: str,
    project_id: int,
    limit: int = 10,
    similarity_threshold: float = 0.3,
    document_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Shared RAG retrieval (used by activity and batch task execution)."""
    from temporal.utils.embeddings import generate_embedding

    logger.info(f"Retrieving RAG context for project {project_id}: {query_text[:50]}...")

    query_embedding = generate_embedding(query_text)
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if document_types:
                doc_types_str = "{" + ",".join([f'"{dt}"' for dt in document_types]) + "}"
                query = """
                    SELECT main.fn_get_enhanced_rag_context(
                        %s::vector(384),
                        %s::bigint,
                        %s::integer,
                        %s::numeric,
                        %s::text[]
                    ) AS result
                """
                cur.execute(
                    query,
                    (embedding_str, project_id, limit, similarity_threshold, doc_types_str),
                )
            else:
                query = """
                    SELECT main.fn_get_enhanced_rag_context(
                        %s::vector(384),
                        %s::bigint,
                        %s::integer,
                        %s::numeric,
                        NULL::text[]
                    ) AS result
                """
                cur.execute(
                    query,
                    (embedding_str, project_id, limit, similarity_threshold),
                )

            row = cur.fetchone()
            if row and row.get("result"):
                result = row["result"]
                logger.info(
                    f"Retrieved {result.get('count', 0)} relevant chunks for project {project_id}"
                )
                return result

    logger.warning(f"No RAG context found for project {project_id}")
    return {
        "results": [],
        "count": 0,
        "similarity_threshold": similarity_threshold,
        "project_id": project_id,
    }


@activity.defn
@track_activity
async def retrieve_rag_context_activity(
    query_text: str,
    project_id: int,
    limit: int = 10,
    similarity_threshold: float = 0.3,  # Lowered from 0.7 - actual similarities are ~0.3-0.35
    document_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Retrieve relevant context using RAG.
    
    Generates query embedding and retrieves enriched chunks with document/project context.
    
    Args:
        query_text: Text query to search for
        project_id: Project ID to filter chunks
        limit: Maximum number of chunks to retrieve
        similarity_threshold: Minimum similarity score (0-1)
        document_types: Optional list of document types to filter by
        
    Returns:
        Dictionary with results, count, and metadata
    """
    try:
        return await retrieve_rag_context_impl(
            query_text, project_id, limit, similarity_threshold, document_types
        )
    except Exception as e:
        import traceback
        logger.error(f"Error retrieving RAG context: {e}")
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise

