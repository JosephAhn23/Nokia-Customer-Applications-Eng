"""
Database connection and session management
Uses connection pooling for optimal performance
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional
import psycopg2
from psycopg2 import pool, sql
from psycopg2.extras import RealDictCursor
import os
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """Database connection manager with connection pooling"""
    
    _connection_pool: Optional[pool.ThreadedConnectionPool] = None
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self._initialize_pool()
    
    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load database configuration"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config.get('database', {})
        except FileNotFoundError:
            logger.warning("Config file not found, using environment variables")
            return {}
    
    def _initialize_pool(self):
        """Initialize connection pool"""
        if self._connection_pool is not None:
            return
        
        db_config = {
            'host': self.config.get('host', os.getenv('NETMON_DB_HOST', 'localhost')),
            'port': self.config.get('port', int(os.getenv('NETMON_DB_PORT', 5432))),
            'database': self.config.get('name', os.getenv('NETMON_DB_NAME', 'netmon')),
            'user': self.config.get('user', os.getenv('NETMON_DB_USER', 'netmon')),
            'password': self.config.get('password', os.getenv('NETMON_DB_PASSWORD', ''))
        }
        
        pool_size = self.config.get('pool_size', 10)
        max_overflow = self.config.get('max_overflow', 20)
        
        try:
            self._connection_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=pool_size + max_overflow,
                **db_config
            )
            logger.info(f"Database connection pool initialized (size: {pool_size})")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Get a connection from the pool"""
        if self._connection_pool is None:
            self._initialize_pool()
        
        conn = None
        try:
            conn = self._connection_pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                self._connection_pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, dict_cursor: bool = True) -> Generator:
        """Get a cursor from the pool"""
        with self.get_connection() as conn:
            cursor_class = RealDictCursor if dict_cursor else psycopg2.extensions.cursor
            cursor = conn.cursor(cursor_factory=cursor_class)
            try:
                yield cursor
            finally:
                cursor.close()
    
    def execute_query(self, query: str, params: Optional[tuple] = None, fetch: bool = True) -> list:
        """Execute a query and return results"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            if fetch:
                return cursor.fetchall()
            return []
    
    def execute_one(self, query: str, params: Optional[tuple] = None) -> Optional[dict]:
        """Execute a query and return single result"""
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()
    
    def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def close_pool(self):
        """Close all connections in the pool"""
        if self._connection_pool:
            self._connection_pool.closeall()
            self._connection_pool = None
            logger.info("Database connection pool closed")


# Global database instance
_db_instance: Optional[DatabaseConnection] = None


def get_db() -> DatabaseConnection:
    """Get global database instance"""
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseConnection()
    return _db_instance


