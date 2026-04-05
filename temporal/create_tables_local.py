"""Create vector tables in the database that Python is actually connecting to."""
import sys
from pathlib import Path

parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

import psycopg2
from temporal.config import config

print("=" * 60)
print("Creating vector tables in the database Python connects to")
print("=" * 60)

# Connect using the same config as the application
conn = psycopg2.connect(
    host=config.database.host,
    port=config.database.port,
    database=config.database.name,
    user=config.database.user,
    password=config.database.password
)

cur = conn.cursor()

# Check current database
cur.execute("SELECT current_database();")
db = cur.fetchone()[0]
print(f"Connected to database: {db}")

# Create main schema if needed
cur.execute("CREATE SCHEMA IF NOT EXISTS main;")
print("✓ Created main schema (if needed)")

# Enable pgvector extension
try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()  # Commit after extension creation
    print("✓ Enabled pgvector extension")
except Exception as e:
    print(f"⚠ Could not enable vector extension: {e}")
    conn.rollback()  # Rollback on error
    print("⚠ Continuing without vector extension (will create table without vector type)")

# Create document_chunk table
cur.execute("""
    CREATE TABLE IF NOT EXISTS main.document_chunk (
        chunk_id          BIGSERIAL,
        document_id       BIGINT NOT NULL,
        project_id        BIGINT NOT NULL,
        chunk_index       INT NOT NULL,
        chunk_text        TEXT NOT NULL,
        chunk_metadata    JSONB,
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")
print("✓ Created main.document_chunk table")

# Create indexes for document_chunk
for index_sql in [
    "CREATE INDEX IF NOT EXISTS idx_document_chunk_document ON main.document_chunk(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunk_project ON main.document_chunk(project_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_chunk_index ON main.document_chunk(document_id, chunk_index);"
]:
    cur.execute(index_sql)
print("✓ Created indexes for document_chunk")

# Create document_embedding table (384 dimensions for Sentence Transformers)
# Check if vector type is available
cur.execute("""
    SELECT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'vector'
    );
""")
has_vector = cur.fetchone()[0]

if has_vector:
    embedding_type = "vector(384)"
    print("✓ Vector type available, using vector(384)")
else:
    embedding_type = "TEXT"  # Fallback to TEXT if vector extension not available
    print("⚠ Vector type not available, using TEXT (you need pgvector extension)")

cur.execute(f"""
    CREATE TABLE IF NOT EXISTS main.document_embedding (
        embedding_id      BIGSERIAL,
        chunk_id          BIGINT NOT NULL,
        document_id       BIGINT NOT NULL,
        project_id        BIGINT NOT NULL,
        embedding         {embedding_type} NOT NULL,
        embedding_model   VARCHAR(100) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
        created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")
print("✓ Created main.document_embedding table")

# Create indexes for document_embedding
for index_sql in [
    "CREATE INDEX IF NOT EXISTS idx_document_embedding_chunk ON main.document_embedding(chunk_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_embedding_document ON main.document_embedding(document_id);",
    "CREATE INDEX IF NOT EXISTS idx_document_embedding_project ON main.document_embedding(project_id);"
]:
    cur.execute(index_sql)
print("✓ Created indexes for document_embedding")

# Create vector similarity index (only if vector type is available)
if has_vector:
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_embedding_vector_hnsw 
            ON main.document_embedding 
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """)
        print("✓ Created HNSW vector similarity index")
    except Exception as e:
        print(f"⚠ Could not create vector index: {e}")
else:
    print("⚠ Skipping vector index (vector type not available)")

conn.commit()

# Verify tables exist
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'main' AND tablename IN ('document_chunk', 'document_embedding') ORDER BY tablename;")
tables = [row[0] for row in cur.fetchall()]
print(f"\n✓ Verified tables exist: {tables}")

cur.close()
conn.close()

print("\n" + "=" * 60)
print("SUCCESS: Tables created in database!")
print("=" * 60)

