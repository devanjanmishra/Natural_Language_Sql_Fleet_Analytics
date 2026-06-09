"""Central configuration, driven by environment variables (see .env.example)."""
import os

# --- MySQL ---
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "fleet")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "fleetpass")
MYSQL_DB = os.getenv("MYSQL_DB", "fleet_insight")

# --- Ollama ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# A small, fast, SQL-capable model. Swap for "sqlcoder", "llama3.1", etc.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

# --- Safety ---
# Only these statement types may ever reach the database.
ALLOWED_SQL_PREFIXES = ("SELECT", "WITH")
MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))

# --- Milvus (optional semantic module) ---
MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
ENABLE_SEMANTIC = os.getenv("ENABLE_SEMANTIC", "false").lower() == "true"
