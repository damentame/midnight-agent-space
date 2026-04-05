"""Test script to simulate store_vectors_activity database operations."""
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

import json
import logging
from temporal.utils.db import get_connection, init_pool, close_pool
from temporal.config import config

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_store_vectors():
    """Simulate exactly what store_vectors_activity does."""
    logger.info("=" * 60)
    logger.info("Testing store_vectors_activity database operations")
    logger.info("=" * 60)
    
    # Initialize connection pool
    logger.info("Initializing connection pool...")
    init_pool()
    
    # Simulate chunks_with_embeddings data
    chunks_with_embeddings = [
        {
            "document_id": 1,
            "project_id": 1,
            "chunk_index": 0,
            "chunk_text": "Test chunk text",
            "chunk_metadata": {"test": "metadata"},
            "embedding": [0.1] * 384  # 384 dimensions for Sentence Transformers
        }
    ]
    
    logger.info(f"Simulating storage of {len(chunks_with_embeddings)} chunks")
    
    try:
        with get_connection() as conn:
            logger.info("Got connection from pool")
            
            # Check current database and search_path
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_setting('search_path');")
                db_name, search_path = cur.fetchone()
                logger.info(f"Connected to database: {db_name}")
                logger.info(f"Current search_path: {search_path}")
                
                # Check if main schema exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_namespace 
                        WHERE nspname = 'main'
                    );
                """)
                schema_exists = cur.fetchone()[0]
                logger.info(f"main schema exists: {schema_exists}")
                
                # Check if table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM pg_tables 
                        WHERE schemaname = 'main' 
                        AND tablename = 'document_chunk'
                    );
                """)
                table_exists = cur.fetchone()[0]
                logger.info(f"main.document_chunk exists: {table_exists}")
                
                # List all schemas
                cur.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema' ORDER BY nspname;")
                schemas = [row[0] for row in cur.fetchall()]
                logger.info(f"Available schemas: {schemas}")
                
                # List all tables in main schema
                cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'main' ORDER BY tablename;")
                main_tables = [row[0] for row in cur.fetchall()]
                logger.info(f"Tables in main schema: {main_tables}")
                
                # Try to find it in any schema
                cur.execute("""
                    SELECT schemaname, tablename 
                    FROM pg_tables 
                    WHERE tablename = 'document_chunk';
                """)
                tables = cur.fetchall()
                logger.info(f"document_chunk found in schemas: {tables}")
                
                if not table_exists:
                    logger.error(f"Table not found in main schema!")
                    logger.error(f"Available schemas: {schemas}")
                    logger.error(f"Tables in main: {main_tables}")
                    logger.error(f"document_chunk locations: {tables}")
                    return
                
                # Now try the exact INSERT that the activity does
                logger.info("Attempting INSERT (exactly as in activity)...")
                for chunk in chunks_with_embeddings:
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
                    logger.info(f"INSERT successful! Result: {result}")
                    if result:
                        chunk_id = result[0]
                        logger.info(f"Got chunk_id: {chunk_id}")
                        
                        # Try inserting embedding
                        embedding = chunk.get("embedding")
                        if embedding:
                            logger.info("Attempting to insert embedding...")
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
                                "all-MiniLM-L6-v2"
                            ))
                            logger.info("Embedding insert successful!")
                            
                            # Clean up test data
                            cur.execute("DELETE FROM main.document_embedding WHERE chunk_id = %s", (chunk_id,))
                            cur.execute("DELETE FROM main.document_chunk WHERE chunk_id = %s", (chunk_id,))
                            logger.info("Test data cleaned up")
            
            logger.info("=" * 60)
            logger.info("SUCCESS: All operations completed!")
            logger.info("=" * 60)
            
    except Exception as e:
        logger.error("=" * 60)
        logger.error("ERROR occurred!")
        logger.error("=" * 60)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        raise
    finally:
        close_pool()
        logger.info("Connection pool closed")


if __name__ == "__main__":
    test_store_vectors()

