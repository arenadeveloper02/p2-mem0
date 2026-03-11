import logging
import os
import sqlite3
import threading
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SQLiteManager:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        # Ensure directory exists for file-based databases
        if db_path != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(db_path))
            if db_dir:  # Only create if there's a directory path (not root)
                os.makedirs(db_dir, exist_ok=True)
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._lock = threading.Lock()
            self._migrate_history_table()
            self._create_history_table()
            self._create_memory_chunk_mapping_table()
        except (sqlite3.OperationalError, OSError) as e:
            logger.error(f"Failed to create SQLite database at {db_path}: {e}")
            raise

    def _migrate_history_table(self) -> None:
        """
        If a pre-existing history table had the old group-chat columns,
        rename it, create the new schema, copy the intersecting data, then
        drop the old table.
        """
        with self._lock:
            try:
                # Start a transaction
                self.connection.execute("BEGIN")
                cur = self.connection.cursor()

                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='history'")
                if cur.fetchone() is None:
                    self.connection.execute("COMMIT")
                    return  # nothing to migrate

                cur.execute("PRAGMA table_info(history)")
                old_cols = {row[1] for row in cur.fetchall()}

                expected_cols = {
                    "id",
                    "memory_id",
                    "old_memory",
                    "new_memory",
                    "event",
                    "created_at",
                    "updated_at",
                    "is_deleted",
                    "actor_id",
                    "role",
                }

                if old_cols == expected_cols:
                    self.connection.execute("COMMIT")
                    return

                logger.info("Migrating history table to new schema (no convo columns).")

                # Clean up any existing history_old table from previous failed migration
                cur.execute("DROP TABLE IF EXISTS history_old")

                # Rename the current history table
                cur.execute("ALTER TABLE history RENAME TO history_old")

                # Create the new history table with updated schema
                cur.execute(
                    """
                    CREATE TABLE history (
                        id           TEXT PRIMARY KEY,
                        memory_id    TEXT,
                        old_memory   TEXT,
                        new_memory   TEXT,
                        event        TEXT,
                        created_at   DATETIME,
                        updated_at   DATETIME,
                        is_deleted   INTEGER,
                        actor_id     TEXT,
                        role         TEXT
                    )
                """
                )

                # Copy data from old table to new table
                intersecting = list(expected_cols & old_cols)
                if intersecting:
                    cols_csv = ", ".join(intersecting)
                    cur.execute(f"INSERT INTO history ({cols_csv}) SELECT {cols_csv} FROM history_old")

                # Drop the old table
                cur.execute("DROP TABLE history_old")

                # Commit the transaction
                self.connection.execute("COMMIT")
                logger.info("History table migration completed successfully.")

            except Exception as e:
                # Rollback the transaction on any error
                self.connection.execute("ROLLBACK")
                logger.error(f"History table migration failed: {e}")
                raise

    def _create_history_table(self) -> None:
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS history (
                        id           TEXT PRIMARY KEY,
                        memory_id    TEXT,
                        old_memory   TEXT,
                        new_memory   TEXT,
                        event        TEXT,
                        created_at   DATETIME,
                        updated_at   DATETIME,
                        is_deleted   INTEGER,
                        actor_id     TEXT,
                        role         TEXT
                    )
                """
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to create history table: {e}")
                raise

    def _create_memory_chunk_mapping_table(self) -> None:
        """Create the memory_chunk_mapping table to store original content for chunked memories."""
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_chunk_mapping (
                        id                    TEXT PRIMARY KEY,
                        original_content      TEXT NOT NULL,
                        original_message_id   TEXT,
                        original_token_count  INTEGER,
                        total_chunks          INTEGER,
                        user_id               TEXT,
                        agent_id              TEXT,
                        run_id                TEXT,
                        created_at            DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )
                # Create index on original_message_id for faster lookups
                self.connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_memory_chunk_mapping_message_id 
                    ON memory_chunk_mapping(original_message_id)
                    """
                )
                # Create index on user_id, agent_id, run_id for filtering
                self.connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_memory_chunk_mapping_filters 
                    ON memory_chunk_mapping(user_id, agent_id, run_id)
                    """
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to create memory_chunk_mapping table: {e}")
                raise

    def add_chunk_mapping(
        self,
        original_content: str,
        original_message_id: Optional[str] = None,
        original_token_count: Optional[int] = None,
        total_chunks: Optional[int] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """
        Add a new entry to memory_chunk_mapping table.
        
        Args:
            original_content: The full original content that was chunked
            original_message_id: The UUID linking all chunks together
            original_token_count: Total token count of the original content
            total_chunks: Total number of chunks created
            user_id: User ID associated with the content
            agent_id: Agent ID associated with the content
            run_id: Run ID associated with the content
            
        Returns:
            str: The mapping ID (primary key)
        """
        mapping_id = str(uuid.uuid4())
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    INSERT INTO memory_chunk_mapping (
                        id, original_content, original_message_id, original_token_count,
                        total_chunks, user_id, agent_id, run_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (
                        mapping_id,
                        original_content,
                        original_message_id,
                        original_token_count,
                        total_chunks,
                        user_id,
                        agent_id,
                        run_id,
                    ),
                )
                self.connection.execute("COMMIT")
                return mapping_id
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to add chunk mapping: {e}")
                raise

    def get_chunk_mapping(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a chunk mapping by ID.
        
        Args:
            mapping_id: The mapping ID to retrieve
            
        Returns:
            Optional[Dict]: The mapping data or None if not found
        """
        with self._lock:
            cur = self.connection.execute(
                """
                SELECT id, original_content, original_message_id, original_token_count,
                       total_chunks, user_id, agent_id, run_id, created_at
                FROM memory_chunk_mapping
                WHERE id = ?
            """,
                (mapping_id,),
            )
            row = cur.fetchone()
            
        if row is None:
            return None
            
        return {
            "id": row[0],
            "original_content": row[1],
            "original_message_id": row[2],
            "original_token_count": row[3],
            "total_chunks": row[4],
            "user_id": row[5],
            "agent_id": row[6],
            "run_id": row[7],
            "created_at": row[8],
        }

    def get_chunk_mapping_by_message_id(self, original_message_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a chunk mapping by original_message_id.
        
        Args:
            original_message_id: The original message ID linking chunks
            
        Returns:
            Optional[Dict]: The mapping data or None if not found
        """
        with self._lock:
            cur = self.connection.execute(
                """
                SELECT id, original_content, original_message_id, original_token_count,
                       total_chunks, user_id, agent_id, run_id, created_at
                FROM memory_chunk_mapping
                WHERE original_message_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (original_message_id,),
            )
            row = cur.fetchone()
            
        if row is None:
            return None
            
        return {
            "id": row[0],
            "original_content": row[1],
            "original_message_id": row[2],
            "original_token_count": row[3],
            "total_chunks": row[4],
            "user_id": row[5],
            "agent_id": row[6],
            "run_id": row[7],
            "created_at": row[8],
        }

    def add_history(
        self,
        memory_id: str,
        old_memory: Optional[str],
        new_memory: Optional[str],
        event: str,
        *,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        is_deleted: int = 0,
        actor_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> None:
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute(
                    """
                    INSERT INTO history (
                        id, memory_id, old_memory, new_memory, event,
                        created_at, updated_at, is_deleted, actor_id, role
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        str(uuid.uuid4()),
                        memory_id,
                        old_memory,
                        new_memory,
                        event,
                        created_at,
                        updated_at,
                        is_deleted,
                        actor_id,
                        role,
                    ),
                )
                self.connection.execute("COMMIT")
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to add history record: {e}")
                raise

    def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self.connection.execute(
                """
                SELECT id, memory_id, old_memory, new_memory, event,
                       created_at, updated_at, is_deleted, actor_id, role
                FROM history
                WHERE memory_id = ?
                ORDER BY created_at ASC, DATETIME(updated_at) ASC
            """,
                (memory_id,),
            )
            rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "memory_id": r[1],
                "old_memory": r[2],
                "new_memory": r[3],
                "event": r[4],
                "created_at": r[5],
                "updated_at": r[6],
                "is_deleted": bool(r[7]),
                "actor_id": r[8],
                "role": r[9],
            }
            for r in rows
        ]

    def reset(self) -> None:
        """Drop and recreate the history and memory_chunk_mapping tables."""
        with self._lock:
            try:
                self.connection.execute("BEGIN")
                self.connection.execute("DROP TABLE IF EXISTS history")
                self.connection.execute("DROP TABLE IF EXISTS memory_chunk_mapping")
                self.connection.execute("COMMIT")
                self._create_history_table()
                self._create_memory_chunk_mapping_table()
            except Exception as e:
                self.connection.execute("ROLLBACK")
                logger.error(f"Failed to reset tables: {e}")
                raise

    def close(self) -> None:
        if hasattr(self, 'connection') and self.connection:
            try:
                self.connection.close()
            except Exception as e:
                logger.warning(f"Error closing SQLite connection: {e}")
            finally:
                self.connection = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass  # Ignore errors during cleanup
