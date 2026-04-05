"""Test script to verify configuration is loading correctly."""
import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from temporal.config import config
import os

print("=" * 60)
print("CONFIGURATION TEST")
print("=" * 60)
print(f"DB_PASSWORD from os.getenv: {os.getenv('DB_PASSWORD', 'NOT SET')}")
print(f"DB_PASSWORD from config: {config.database.password}")
print(f"Database connection: {config.database.connection_string.replace(config.database.password, '***') if config.database.password else config.database.connection_string}")
print(f"Temporal address: {config.temporal.address}")
print(f"OpenAI API key set: {'Yes' if config.openai.api_key and config.openai.api_key != 'your_openai_api_key_here' else 'No'}")
print("=" * 60)

if not config.database.password:
    print("\n⚠️  WARNING: Database password is not set!")
    print("Make sure temporal/.env file exists and contains:")
    print("  DB_PASSWORD=7714")
else:
    print("\n[OK] Configuration loaded successfully!")
