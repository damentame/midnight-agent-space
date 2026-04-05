"""Embedding generation utilities with support for multiple providers."""
import time
from typing import List, Dict, Any, Optional
import logging

from temporal.config import config

logger = logging.getLogger(__name__)

# Initialize clients
_openai_client = None
_sentence_transformers_model = None


def _get_openai_client():
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            # Try to get API key from config first, then fall back to environment variable
            api_key = config.openai.api_key
            if not api_key:
                # Fallback: read directly from environment
                import os
                api_key = os.getenv("OPENAI_API_KEY", "")
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set in configuration or environment variables")
            
            _openai_client = OpenAI(api_key=api_key)
        except ImportError:
            raise ValueError("openai package not installed. Install with: pip install openai")
    return _openai_client


def _get_sentence_transformers_model():
    """Get or create Sentence Transformers model."""
    global _sentence_transformers_model
    if _sentence_transformers_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = config.embedding.sentence_transformers_model
            logger.info(f"Loading Sentence Transformers model: {model_name}")
            _sentence_transformers_model = SentenceTransformer(model_name)
            logger.info(f"Model loaded successfully. Embedding dimension: {_sentence_transformers_model.get_sentence_embedding_dimension()}")
        except ImportError:
            raise ValueError("sentence-transformers package not installed. Install with: pip install sentence-transformers")
        except Exception as e:
            logger.error(f"Failed to load Sentence Transformers model: {e}")
            raise
    return _sentence_transformers_model


def _generate_openai_embeddings(texts: List[str], model: Optional[str] = None) -> List[List[float]]:
    """Generate embeddings using OpenAI API."""
    import openai
    client = _get_openai_client()
    model = model or config.openai.embedding_model
    
    try:
        response = client.embeddings.create(
            model=model,
            input=texts
        )
        return [item.embedding for item in response.data]
    except openai.RateLimitError as e:
        logger.error(f"OpenAI rate limit/quota exceeded: {e}")
        raise
    except Exception as e:
        logger.error(f"OpenAI embedding generation failed: {e}")
        raise


def _generate_sentence_transformers_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using Sentence Transformers (local, free)."""
    model = _get_sentence_transformers_model()
    
    try:
        # Sentence Transformers handles batching automatically
        embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=False)
        # Convert to list of lists
        return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings]
    except Exception as e:
        logger.error(f"Sentence Transformers embedding generation failed: {e}")
        raise


def _generate_ollama_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using Ollama (local)."""
    import httpx
    import os
    
    ollama_url = config.embedding.ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = config.embedding.ollama_embedding_model
    
    embeddings = []
    for text in texts:
        try:
            response = httpx.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            embeddings.append(data.get("embedding", []))
        except Exception as e:
            logger.error(f"Ollama embedding generation failed for text: {e}")
            raise
    
    return embeddings


def _generate_huggingface_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using Hugging Face Inference API."""
    import httpx
    import os
    
    api_key = config.embedding.huggingface_api_key or os.getenv("HUGGINGFACE_API_KEY", "")
    if not api_key:
        raise ValueError("HUGGINGFACE_API_KEY not set")
    
    model = config.embedding.huggingface_model
    url = f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model}"
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = httpx.post(
            url,
            headers=headers,
            json={"inputs": texts},
            timeout=30.0
        )
        response.raise_for_status()
        embeddings = response.json()
        
        # Handle single text (returns 1D) vs batch (returns 2D)
        if isinstance(embeddings[0], list):
            return embeddings
        else:
            return [embeddings]
    except Exception as e:
        logger.error(f"Hugging Face embedding generation failed: {e}")
        raise


def generate_embedding(text: str, model: Optional[str] = None) -> List[float]:
    """
    Generate embedding for a single text.
    
    Args:
        text: Text to embed
        model: Embedding model name (only used for OpenAI)
        
    Returns:
        List of floats representing the embedding vector
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for embedding")
        # Return zero vector with appropriate dimension based on provider
        provider = config.embedding.provider.lower()
        if provider == "openai":
            return [0.0] * config.openai.embedding_dimensions
        elif provider in ["sentence_transformers", "sentence-transformers"]:
            return [0.0] * 384  # all-MiniLM-L6-v2 default
        elif provider == "ollama":
            return [0.0] * 768  # nomic-embed-text default
        else:
            return [0.0] * 384  # Safe default
    
    embeddings = generate_embeddings_batch([text], model=model)
    return embeddings[0] if embeddings else [0.0] * 384


def generate_embeddings_batch(
    texts: List[str],
    model: Optional[str] = None,
    batch_size: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_delay: Optional[float] = None
) -> List[List[float]]:
    """
    Generate embeddings for multiple texts using the configured provider.
    
    Args:
        texts: List of texts to embed
        model: Embedding model name (only used for OpenAI)
        batch_size: Number of texts per API call (only used for OpenAI)
        max_retries: Maximum retry attempts (only used for API providers)
        retry_delay: Delay between retries in seconds
        
    Returns:
        List of embedding vectors
    """
    if not texts:
        return []
    
    # Get provider from config, with fallback to environment variable
    try:
        provider = config.embedding.provider.lower()
    except Exception:
        provider = "openai"  # Default fallback
    
    # Double-check: read directly from environment if config doesn't have it
    import os
    env_provider = os.getenv("EMBEDDING_PROVIDER", "").lower()
    if env_provider and (not provider or provider == "openai"):
        provider = env_provider
        logger.info(f"Using embedding provider from environment: {provider}")
    
    logger.info(f"Using embedding provider: {provider}")
    
    batch_size = batch_size or config.embedding.batch_size
    max_retries = max_retries or config.embedding.max_retries
    retry_delay = retry_delay or config.embedding.retry_delay
    
    # Filter empty texts
    texts = [text.strip() if text else "" for text in texts]
    texts = [t for t in texts if t]  # Remove empty strings
    
    if not texts:
        return []
    
    # Route to appropriate provider
    if provider == "openai":
        logger.warning("Using OpenAI provider - if you want to use Sentence Transformers, set EMBEDDING_PROVIDER=sentence_transformers in .env and restart worker")
        return _generate_openai_embeddings_with_retry(texts, model, batch_size, max_retries, retry_delay)
    elif provider == "sentence_transformers" or provider == "sentence-transformers":
        logger.info(f"Using Sentence Transformers provider with model: {config.embedding.sentence_transformers_model}")
        return _generate_sentence_transformers_embeddings(texts)
    elif provider == "ollama":
        logger.info(f"Using Ollama provider with model: {config.embedding.ollama_embedding_model}")
        return _generate_ollama_embeddings(texts)
    elif provider == "huggingface" or provider == "hugging_face":
        logger.info(f"Using Hugging Face provider with model: {config.embedding.huggingface_model}")
        return _generate_huggingface_embeddings(texts)
    else:
        raise ValueError(f"Unknown embedding provider: {provider}. Supported: openai, sentence_transformers, ollama, huggingface")


def _generate_openai_embeddings_with_retry(
    texts: List[str],
    model: Optional[str],
    batch_size: int,
    max_retries: int,
    retry_delay: float
) -> List[List[float]]:
    """Generate OpenAI embeddings with retry logic."""
    import openai
    
    all_embeddings = []
    
    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        # Retry logic
        retries = 0
        while retries <= max_retries:
            try:
                embeddings = _generate_openai_embeddings(batch, model)
                all_embeddings.extend(embeddings)
                logger.info(f"Generated embeddings for batch {i // batch_size + 1}")
                break
                
            except openai.RateLimitError as e:
                retries += 1
                if retries > max_retries:
                    logger.error(f"OpenAI rate limit/quota exceeded after {max_retries} retries")
                    logger.error("Consider switching to a different embedding provider (sentence_transformers, ollama, etc.)")
                    raise
                wait_time = retry_delay * (2 ** retries)  # Exponential backoff
                logger.warning(f"Rate limited, waiting {wait_time}s before retry {retries}/{max_retries}")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch: {e}")
                if retries >= max_retries:
                    raise
                retries += 1
                time.sleep(retry_delay * retries)
    
    return all_embeddings


def add_embeddings_to_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add embeddings to chunk dictionaries.
    
    Args:
        chunks: List of chunk dictionaries with 'chunk_text' key
        
    Returns:
        List of chunks with 'embedding' key added
    """
    texts = [chunk["chunk_text"] for chunk in chunks]
    embeddings = generate_embeddings_batch(texts)
    
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding
    
    return chunks
