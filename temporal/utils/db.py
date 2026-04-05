"""Database connection and query utilities."""
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
import logging

from temporal.config import config

logger = logging.getLogger(__name__)

# Connection pool
_pool: Optional[ThreadedConnectionPool] = None


def init_pool(min_conn: int = 1, max_conn: int = 10):
    """Initialize database connection pool."""
    global _pool
    if _pool is None:
        try:
            # Initialize connection pool with search_path option
            # The options parameter sets PostgreSQL connection parameters
            _pool = ThreadedConnectionPool(
                min_conn,
                max_conn,
                host=config.database.host,
                port=config.database.port,
                database=config.database.name,
                user=config.database.user,
                password=config.database.password,
                options="-c search_path=main,public"  # Set default search_path for all connections
            )
            logger.info(f"Database connection pool initialized for {config.database.host}:{config.database.port}/{config.database.name}")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    return _pool


def get_pool() -> ThreadedConnectionPool:
    """Get database connection pool, initializing if needed."""
    if _pool is None:
        return init_pool()
    return _pool


@contextmanager
def get_connection():
    """Get a database connection from the pool."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        # Set search_path to include 'main' schema so we can access main.* tables
        # This must be done on every connection as search_path is session-specific
        # We set it immediately when getting a connection from the pool
        with conn.cursor() as cur:
            # Set search_path - this must be done before any queries
            cur.execute("SET search_path TO main, public, \"$user\";")
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        pool.putconn(conn)


def execute_query(query: str, params: Optional[tuple] = None, fetch: bool = True) -> List[Dict[str, Any]]:
    """Execute a SELECT query and return results."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if fetch:
                return [dict(row) for row in cur.fetchall()]
            return []


def execute_procedure(procedure_name: str, params: Optional[tuple] = None) -> Optional[Dict[str, Any]]:
    """Execute a stored procedure and return result."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.callproc(procedure_name, params)
            result = cur.fetchone()
            return dict(result) if result else None


def execute_function(function_name: str, params: Optional[tuple] = None) -> Any:
    """Execute a database function and return result."""
    if params is None:
        params = ()
    
    # Build query with correct number of placeholders
    if len(params) == 0:
        query = f"SELECT {function_name}() AS result"
    else:
        placeholders = ", ".join(["%s"] * len(params))
        query = f"SELECT {function_name}({placeholders}) AS result"
    
    result = execute_query(query, params)
    if result and len(result) > 0:
        row = result[0]
        if row is None:
            return None
        # Handle both dict access and direct value
        if isinstance(row, dict):
            return row.get('result')
        else:
            # If it's not a dict, return the first value
            return row[0] if len(row) > 0 else None
    return None


def insert_many(table: str, columns: List[str], values: List[tuple]) -> None:
    """Insert multiple rows efficiently."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            columns_str = ", ".join(columns)
            query = f"INSERT INTO {table} ({columns_str}) VALUES %s"
            execute_values(cur, query, values)
            conn.commit()


def close_pool():
    """Close the database connection pool."""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed")

