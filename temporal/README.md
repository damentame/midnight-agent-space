# Temporal Document Serialization with RAG

This directory contains a Temporal.io workflow implementation for document serialization with RAG (Retrieval Augmented Generation) capabilities.

## Overview

This system converts the n8n document serialization workflow to Temporal.io, adding:
- **Semantic chunking** of documents
- **Vector embeddings** using OpenAI
- **pgvector storage** for similarity search
- **RAG capabilities** for agent context retrieval

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose
- Python 3.10+
- PostgreSQL with pgvector extension (already set up in your Docker container)
- OpenAI API key

### 2. Setup

```bash
# Navigate to temporal directory
cd temporal

# Create .env file with your configuration
# Copy this template and fill in your values:

# Database Connection (reuse existing Docker container)
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=midnight_agent_space_dev
# DB_USER=postgres
# DB_PASSWORD=your_password_here

# OpenAI Configuration
# OPENAI_API_KEY=your_openai_api_key_here
# OPENAI_EMBEDDING_MODEL=text-embedding-3-small
# OPENAI_EMBEDDING_DIMENSIONS=1536

# Cursor API Configuration (optional)
# CURSOR_API_KEY=your_cursor_api_key_here
# CURSOR_API_URL=https://api.cursor.com/v0

# Temporal Configuration
# TEMPORAL_HOST=localhost
# TEMPORAL_PORT=7233
# TEMPORAL_NAMESPACE=default

# Chunking Configuration
# CHUNK_SIZE=1000
# CHUNK_OVERLAP=200

# Embedding Configuration
# EMBEDDING_BATCH_SIZE=100
# EMBEDDING_MAX_RETRIES=3
# EMBEDDING_RETRY_DELAY=1.0

# Install Python dependencies
pip install -r requirements.txt

# Create vector tables in database
psql -h localhost -U postgres -d midnight_agent_space_dev -f schema/vector_tables.sql
```

### 3. Start Temporal Services (with persistence)

Use the provided Compose file so **workflow history and run data persist** across container restarts (stored in PostgreSQL and named Docker volumes).

```bash
# Ensure the Docker network exists (create it from project root if needed)
docker network create midnightagentspace_default 2>nul || true

# From project root, or from temporal/ with -f docker-compose.temporal.yml
docker compose -f temporal/docker-compose.temporal.yml up -d

# Verify services are running
docker ps | findstr temporal
```

Access Temporal UI at: http://localhost:8080

**Important:** Do not run `docker compose down -v` if you want to keep workflow history (the `-v` flag removes volumes and deletes all persisted data).

### 4. Start Worker

```bash
# In one terminal, start the worker
python worker.py
```

### 5. Run Workflow

```bash
# In another terminal, start a workflow
python main.py <agent_id> <project_id>

# Example:
python main.py 2 1
```

## Configuration

See `.env.example` for all configuration options:

- **Database**: Connection to your existing PostgreSQL container
- **OpenAI**: API key and embedding model settings
- **Chunking**: Chunk size, overlap, separators
- **Temporal**: Server connection settings

## Architecture

```
Workflow Start
    ↓
Spin Up Agent
    ↓
Get Project Documents
    ↓
For Each Document:
    ├─ Chunk Document (semantic splitting)
    ├─ Generate Embeddings (OpenAI)
    ├─ Store Vectors (database)
    ├─ Serialize Document (Cursor API or local LLM)
    └─ Update Document Status
    ↓
Workflow Complete
```

## Key Components

### Workflows
- `workflows/document_serialization_workflow.py` - Main workflow orchestration

### Activities
- `activities/agent_activities.py` - Agent management
- `activities/document_activities.py` - Document processing and RAG
- `activities/api_activities.py` - Cursor API and local LLM integration

### Utilities
- `utils/chunking.py` - Semantic document chunking
- `utils/embeddings.py` - OpenAI embedding generation
- `utils/vector_utils.py` - Vector similarity search
- `utils/db.py` - Database connection management

## RAG Documentation

Comprehensive guides are available in the `docs/` directory:

1. **[RAG Overview](docs/RAG_OVERVIEW.md)** - High-level RAG concepts
2. **[Chunking Guide](docs/01_CHUNKING_GUIDE.md)** - Document splitting
3. **[Embeddings Guide](docs/02_EMBEDDINGS_GUIDE.md)** - Vector generation
4. **[Vector Storage Guide](docs/03_VECTOR_STORAGE_GUIDE.md)** - Database schema
5. **[Similarity Search Guide](docs/04_SIMILARITY_SEARCH_GUIDE.md)** - Querying vectors
6. **[RAG Workflow Guide](docs/05_RAG_WORKFLOW_GUIDE.md)** - Complete pipeline
7. **[Troubleshooting](docs/06_TROUBLESHOOTING.md)** - Common issues
8. **[Examples](docs/07_EXAMPLES.md)** - Code samples

## Database Schema

The system uses two new tables:

- **`main.document_chunk`**: Stores document chunks with metadata
- **`main.document_embedding`**: Stores vector embeddings (1536 dimensions)

See `schema/vector_tables.sql` for full schema definition.

## Usage Examples

### Start Workflow via Python

```python
from client import start_document_serialization

workflow_id = await start_document_serialization(
    agent_id=2,
    project_id=1,
    use_cursor_api=True
)
```

### Search Similar Chunks

```python
from utils.vector_utils import search_similar_chunks

results = search_similar_chunks(
    query_text="user authentication requirements",
    project_id=1,
    limit=10
)
```

### Chunk a Document

```python
from utils.chunking import chunk_document

chunks = chunk_document(
    text="Your document text...",
    document_id=45,
    project_id=1
)
```

## Temporal persistence (full record of workflow runs)

Workflow history is stored in **PostgreSQL** (`temporal-postgres` container) and survives container restarts as long as you use the provided Compose file and do not remove volumes.

### How it works

| Volume / store | Purpose |
|----------------|--------|
| `temporal-postgres-data` | Workflow execution history, visibility (search), namespaces (primary persistence) |
| `temporal-data` | Temporal server local state |

The Compose file configures Temporal to use PostgreSQL for both the main store and visibility (same DB, different schemas). Always start Temporal via `docker compose -f temporal/docker-compose.temporal.yml up -d` so this persistence is used; do not rely on in-memory or ephemeral setups (e.g. `temporal server start-dev` with default SQLite) if you need a full record.

### Keeping your data

- **Restarting containers:** `docker compose -f temporal/docker-compose.temporal.yml restart` keeps data; volumes are preserved.
- **Stopping:** `docker compose -f temporal/docker-compose.temporal.yml down` (without `-v`) keeps volumes; data remains for the next `up`.
- **Removing data:** `docker compose -f temporal/docker-compose.temporal.yml down -v` deletes the volumes and all workflow history; use only when you intend to reset.

### Backup (optional)

To back up the Temporal database (e.g. before upgrades or for disaster recovery):

```bash
# Linux/macOS
docker exec temporal-postgres pg_dump -U postgres temporal > temporal_backup_$(date +%Y%m%d).sql

# Windows PowerShell
docker exec temporal-postgres pg_dump -U postgres temporal > temporal_backup_$(Get-Date -Format "yyyyMMdd").sql
```

Restore (only when the Temporal service is stopped and you are sure you want to overwrite):

```bash
docker compose -f temporal/docker-compose.temporal.yml stop temporal temporal-ui
cat temporal_backup_YYYYMMDD.sql | docker exec -i temporal-postgres psql -U postgres -d temporal
docker compose -f temporal/docker-compose.temporal.yml start temporal temporal-ui
```

## Monitoring

### Temporal UI

Access workflow execution details at:
- URL: http://localhost:8080
- View workflow history, activity logs, and retries

### Database Queries

```sql
-- Check chunks created
SELECT COUNT(*) FROM main.document_chunk WHERE project_id = 1;

-- Check embeddings
SELECT COUNT(*) FROM main.document_embedding WHERE project_id = 1;

-- Test similarity search
SELECT 
    chunk_text,
    embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM main.document_chunk dc
JOIN main.document_embedding de ON dc.chunk_id = de.chunk_id
ORDER BY distance
LIMIT 5;
```

## Troubleshooting

See [Troubleshooting Guide](docs/06_TROUBLESHOOTING.md) for:
- Common errors and solutions
- Debugging techniques
- Performance optimization

## Development

### Running Tests

```bash
# Unit tests (when implemented)
pytest tests/
```

### Code Structure

```
temporal/
├── workflows/          # Temporal workflow definitions
├── activities/         # Activity implementations
├── utils/             # Utility functions (RAG, DB, etc.)
├── schema/            # Database schema files
├── docs/              # Comprehensive documentation
└── tests/             # Test files
```

## Differences from n8n Workflow

1. **RAG Integration**: Documents are chunked and embedded during serialization
2. **Vector Storage**: Chunks and embeddings stored in database for later retrieval
3. **Observability**: Temporal UI provides better visibility than n8n
4. **Error Handling**: More robust retry and error handling
5. **Scalability**: Temporal handles workflow execution at scale

## Next Steps

1. Read the [RAG Overview](docs/RAG_OVERVIEW.md) to understand the system
2. Review [Examples](docs/07_EXAMPLES.md) for code samples
3. Start with a simple workflow execution
4. Explore similarity search capabilities

## Support

For issues or questions:
- Check [Troubleshooting Guide](docs/06_TROUBLESHOOTING.md)
- Review component-specific guides in `docs/`
- Check Temporal UI for workflow execution details

