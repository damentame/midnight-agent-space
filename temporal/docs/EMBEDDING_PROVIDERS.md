# Embedding Providers Guide

This guide explains how to use different embedding providers when OpenAI quota is exceeded or you want to use free/local alternatives.

## Supported Providers

1. **OpenAI** (default) - Cloud-based, requires API key and quota
2. **Sentence Transformers** - Local, free, recommended alternative
3. **Ollama** - Local, free, requires Ollama server
4. **Hugging Face** - Cloud-based, free tier available

## Quick Start: Switch to Sentence Transformers (Recommended)

Sentence Transformers is the easiest free alternative - it runs locally and requires no API keys.

### 1. Install the package

```bash
pip install sentence-transformers
```

### 2. Update your `.env` file

Add or update these lines in `temporal/.env`:

```env
# Switch to Sentence Transformers
EMBEDDING_PROVIDER=sentence_transformers

# Optional: Choose a different model (default is all-MiniLM-L6-v2)
# Other good options:
# - all-mpnet-base-v2 (better quality, slower)
# - all-MiniLM-L6-v2 (fast, good quality) - default
# - paraphrase-multilingual-MiniLM-L12-v2 (multilingual)
SENTENCE_TRANSFORMERS_MODEL=all-MiniLM-L6-v2
```

### 3. Restart your worker

```bash
cd temporal
python worker.py
```

The first run will download the model (one-time, ~90MB). Subsequent runs are instant.

## Provider Details

### Sentence Transformers (Recommended for Free)

**Pros:**
- ✅ Completely free
- ✅ Runs locally (no API calls)
- ✅ Fast after initial model download
- ✅ Good quality embeddings
- ✅ No rate limits

**Cons:**
- ❌ Requires ~500MB disk space for models
- ❌ First run downloads model
- ❌ Slightly slower than API calls (but still fast)

**Configuration:**
```env
EMBEDDING_PROVIDER=sentence_transformers
SENTENCE_TRANSFORMERS_MODEL=all-MiniLM-L6-v2
```

**Popular Models:**
- `all-MiniLM-L6-v2` - Fast, 384 dimensions (default)
- `all-mpnet-base-v2` - Better quality, 768 dimensions
- `paraphrase-multilingual-MiniLM-L12-v2` - Multilingual support

### Ollama (Local Alternative)

**Pros:**
- ✅ Free and local
- ✅ No API keys needed
- ✅ Can use various embedding models

**Cons:**
- ❌ Requires Ollama server running
- ❌ Slower than Sentence Transformers
- ❌ More setup required

**Setup:**
1. Install Ollama: https://ollama.ai
2. Pull embedding model: `ollama pull nomic-embed-text`
3. Start Ollama server: `ollama serve`

**Configuration:**
```env
EMBEDDING_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### Hugging Face (Free Tier Available)

**Pros:**
- ✅ Free tier available
- ✅ Good quality models
- ✅ Cloud-based (no local setup)

**Cons:**
- ❌ Requires API key (free tier available)
- ❌ Rate limits on free tier
- ❌ Slower than local options

**Setup:**
1. Get free API key: https://huggingface.co/settings/tokens
2. Configure:

```env
EMBEDDING_PROVIDER=huggingface
HUGGINGFACE_API_KEY=your_api_key_here
HUGGINGFACE_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

### OpenAI (Original)

**Configuration:**
```env
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=1536
```

## Embedding Dimensions

Different providers/models produce different embedding dimensions:

| Provider | Model | Dimensions |
|----------|-------|------------|
| OpenAI | text-embedding-3-small | 1536 |
| OpenAI | text-embedding-3-large | 3072 |
| Sentence Transformers | all-MiniLM-L6-v2 | 384 |
| Sentence Transformers | all-mpnet-base-v2 | 768 |
| Ollama | nomic-embed-text | 768 |

**Important:** If you switch providers, you may need to:
1. Update your database schema if dimension changes
2. Re-generate embeddings for existing documents
3. Update `OPENAI_EMBEDDING_DIMENSIONS` in config if using OpenAI

## Switching Providers

To switch providers, simply update `EMBEDDING_PROVIDER` in your `.env` file and restart the worker:

```env
# Switch from OpenAI to Sentence Transformers
EMBEDDING_PROVIDER=sentence_transformers
```

The system will automatically use the new provider for all embedding operations.

## Troubleshooting

### "sentence-transformers package not installed"
```bash
pip install sentence-transformers
```

### "Model download failed"
- Check internet connection
- Try a different model (smaller models download faster)
- Models are cached in `~/.cache/torch/sentence_transformers/`

### "Ollama connection failed"
- Ensure Ollama server is running: `ollama serve`
- Check `OLLAMA_URL` in `.env` matches your Ollama server
- Verify model is pulled: `ollama list`

### "Hugging Face API key invalid"
- Get a free API key: https://huggingface.co/settings/tokens
- Ensure `HUGGINGFACE_API_KEY` is set in `.env`

## Performance Comparison

| Provider | Speed | Cost | Quality | Setup |
|----------|-------|------|---------|-------|
| Sentence Transformers | Fast | Free | Good | Easy |
| Ollama | Medium | Free | Good | Medium |
| Hugging Face | Medium | Free tier | Good | Easy |
| OpenAI | Fast | Paid | Excellent | Easy |

## Recommendation

For most use cases, **Sentence Transformers** is the best free alternative:
- No API keys needed
- Fast and reliable
- Good quality embeddings
- Easy setup

