"""Shared pytest fixtures for test suite."""
import tempfile
from pathlib import Path

import pytest_asyncio

from Features.Core.db import db as db_module
from Features.Core.db.db import init_db


@pytest_asyncio.fixture
async def db():
    """Fixture providing a fresh SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    await init_db(db_path)

    yield db_path

    # Close all pooled connections before unlinking (required on Windows).
    pool = db_module._pools.pop(db_path, None)
    if pool is not None:
        while not pool.empty():
            conn = pool.get_nowait()
            await conn.close()

    db_path.unlink(missing_ok=True)
