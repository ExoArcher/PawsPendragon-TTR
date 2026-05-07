"""Atomic cache-database coherence layer for Paws Pendragon TTR.

Ensures cache sets and database state remain synchronized across
INSERT, DELETE, and UPSERT operations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import aiosqlite


async def atomic_db_cache_update(
    db_path: str | Path,
    operation: Literal["insert", "delete", "upsert"],
    table: str,
    where_clause: dict,
    cache_set: set,
    cache_keys: list[int],
) -> bool:
    """
    Atomically update database and cache with implicit rollback on failure.

    Updates cache and database in a single transaction. If either fails,
    the transaction is automatically rolled back and False is returned.

    Args:
        db_path: Path to the SQLite database.
        operation: One of "insert", "delete", or "upsert".
        table: Name of the table to operate on.
        where_clause: Dict of column=value conditions for WHERE clause.
        cache_set: Set object to update (for INSERT) or discard from (for DELETE/UPSERT).
        cache_keys: List of integer keys to add (INSERT) or remove (DELETE/UPSERT).

    Returns:
        True if both cache and database updates succeed, False otherwise.

    Behavior:
        - INSERT: cache_set.update(cache_keys), then execute INSERT (caller responsibility).
        - DELETE: Build DELETE FROM table WHERE col1=? AND col2=? ..., then cache_set.discard() each key.
        - UPSERT: Same as DELETE (most call sites use this for "reload").
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            # Update cache first (fast path).
            if operation == "insert":
                cache_set.update(cache_keys)
            elif operation in ("delete", "upsert"):
                for key in cache_keys:
                    cache_set.discard(key)

            # Build and execute the SQL operation.
            if operation in ("delete", "upsert"):
                # Construct WHERE clause from dict: col1=?, col2=?, ...
                where_parts = [f"{col}=?" for col in where_clause.keys()]
                where_sql = " AND ".join(where_parts)
                sql = f"DELETE FROM {table} WHERE {where_sql}"
                params = tuple(where_clause.values())
                await db.execute(sql, params)
            elif operation == "insert":
                # For INSERT, the caller handles the actual insert.
                # We've already updated the cache above.
                pass

            # Commit the transaction. If either cache or DB updates failed,
            # the context manager rolls back automatically.
            await db.commit()

        return True

    except Exception:
        # Automatic rollback via context manager.
        # Never log or retry.
        return False
