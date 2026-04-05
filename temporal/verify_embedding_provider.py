"""Quick script to verify embedding provider configuration."""
import os
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

print("=" * 60)
print("Embedding Provider Configuration Check")
print("=" * 60)
print()

# Check environment variable
env_provider = os.getenv("EMBEDDING_PROVIDER", "NOT SET")
print(f"Environment Variable (EMBEDDING_PROVIDER): {env_provider}")
print()

# Check config
try:
    from temporal.config import config
    config_provider = config.embedding.provider
    print(f"Config Value (config.embedding.provider): {config_provider}")
    print()
    
    if config_provider.lower() != env_provider.lower():
        print("⚠️  WARNING: Config and environment don't match!")
        print(f"   Config says: {config_provider}")
        print(f"   Environment says: {env_provider}")
        print()
        print("   This usually means the worker needs to be restarted.")
        print("   The config instance was created before .env was updated.")
        print()
    else:
        print("✅ Config and environment match!")
        print()
        
except Exception as e:
    print(f"❌ Error loading config: {e}")
    print()

# Check if sentence-transformers is installed
try:
    import sentence_transformers
    print("✅ sentence-transformers package is installed")
    print(f"   Version: {sentence_transformers.__version__}")
except ImportError:
    print("❌ sentence-transformers package is NOT installed")
    print("   Install with: pip install sentence-transformers")
    
print()
print("=" * 60)
print("Recommendation:")
if env_provider.lower() == "sentence_transformers":
    print("  1. Make sure sentence-transformers is installed")
    print("  2. RESTART your worker to pick up the new config")
    print("  3. The worker will use Sentence Transformers for embeddings")
else:
    print(f"  Set EMBEDDING_PROVIDER=sentence_transformers in .env")
print("=" * 60)

