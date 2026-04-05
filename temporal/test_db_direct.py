"""Direct database connection test to see what we're actually connecting to."""
import psycopg2

# Connect directly - use port 5434 to connect to Docker container
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from temporal.config import config

# Connect using config (which reads from .env)
conn = psycopg2.connect(
    host=config.database.host,
    port=config.database.port,
    database=config.database.name,
    user=config.database.user,
    password=config.database.password
)

cur = conn.cursor()

# Check database
cur.execute("SELECT current_database();")
db = cur.fetchone()[0]
print(f"Connected to database: {db}")

# Check schemas
cur.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname != 'information_schema' ORDER BY nspname;")
schemas = [row[0] for row in cur.fetchall()]
print(f"Available schemas: {schemas}")

# Check tables in main
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'main' ORDER BY tablename;")
tables = [row[0] for row in cur.fetchall()]
print(f"Tables in main schema ({len(tables)}): {tables}")

# Specifically check for document_chunk
cur.execute("SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'main' AND tablename = 'document_chunk');")
exists = cur.fetchone()[0]
print(f"document_chunk exists in main: {exists}")

# Try to query it directly
if exists:
    try:
        cur.execute("SELECT COUNT(*) FROM main.document_chunk;")
        count = cur.fetchone()[0]
        print(f"document_chunk row count: {count}")
    except Exception as e:
        print(f"Error querying document_chunk: {e}")

cur.close()
conn.close()

