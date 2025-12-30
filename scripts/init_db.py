#!/usr/bin/env python
"""
Initialize the database by creating all tables
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from d4bl.database import init_db, create_tables, close_db


async def main():
    """Initialize database tables"""
    print("Initializing database...")
    try:
        init_db()
        await create_tables()
        print("✓ Database tables created successfully!")
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())


