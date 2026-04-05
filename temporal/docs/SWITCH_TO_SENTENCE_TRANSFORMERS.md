# Switching to Sentence Transformers - Complete Guide

## ✅ What Has Been Done

1. ✅ **Code Updated** - Added support for multiple embedding providers
2. ✅ **Configuration Added** - `.env` file updated with `EMBEDDING_PROVIDER=sentence_transformers`
3. ✅ **Migration Script Created** - `migrate_embeddings.ps1` to update database schema

## 📋 Next Steps

### Step 1: Install Sentence Transformers

```powershell
pip install sentence-transformers
```

### Step 2: Run Database Migration

The database schema needs to be updated from 1536 dimensions (OpenAI) to 384 dimensions (Sentence Transformers).

**Option A: Clear existing embeddings and migrate**
```powershell
cd temporal
.\migrate_embeddings.ps1 -ClearExisting
```

**Option B: Keep existing embeddings (they'll need regeneration)**
```powershell
cd temporal
.\migrate_embeddings.ps1
```

**Note:** If you have existing embeddings, they will be incompatible with the new dimension. You'll need to regenerate them by running your workflow again.

### Step 3: Restart Your Worker

```powershell
cd temporal
python worker.py
```

The first run will download the Sentence Transformers model (~90MB, one-time download).

### Step 4: Test Your Workflow

Run your workflow as usual:
```powershell
python test_workflow.py 2 1
```

## 🔍 Verification

Check that everything is working:

1. **Check .env configuration:**
   ```powershell
   Get-Content .env | Select-String -Pattern "EMBEDDING_PROVIDER"
   ```
   Should show: `EMBEDDING_PROVIDER=sentence_transformers`

2. **Check database schema:**
   ```powershell
   docker exec pgvector-postgres psql -U postgres -d midnight_agent_space_dev -c "SELECT column_name, data_type, udt_name FROM information_schema.columns WHERE table_schema = 'main' AND table_name = 'document_embedding' AND column_name = 'embedding';"
   ```
   Should show: `vector(384)`

3. **Check worker logs:**
   Look for: `"Loading Sentence Transformers model: all-MiniLM-L6-v2"`

## 🎯 Benefits

- ✅ **Free** - No API costs
- ✅ **No Rate Limits** - Runs locally
- ✅ **Fast** - After initial model download
- ✅ **Good Quality** - Suitable for most RAG use cases

## 🔄 Switching Back to OpenAI

If you want to switch back to OpenAI later:

1. Update `.env`:
   ```env
   EMBEDDING_PROVIDER=openai
   OPENAI_EMBEDDING_DIMENSIONS=1536
   ```

2. Run migration back to 1536 dimensions (or create new migration script)

3. Restart worker

## 📚 More Information

See `docs/EMBEDDING_PROVIDERS.md` for details on all supported providers.

