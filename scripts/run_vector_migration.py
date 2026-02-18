#!/usr/bin/env python3
"""
Script to run the vector database migration for Supabase.
This enables the pgvector extension and creates the scraped_content_vectors table.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker

from d4bl.infra.database import get_database_url


def split_sql_statements(sql: str) -> list[str]:
    """Split SQL into statements, respecting dollar-quoted blocks ($$...$$)."""
    statements = []
    current = []
    in_dollar_quote = False

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue

        # Track $$ delimiters to avoid splitting inside function bodies
        dollar_count = line.count("$$")
        if dollar_count % 2 == 1:
            in_dollar_quote = not in_dollar_quote

        current.append(line)

        # Only split on semicolons when outside $$ blocks
        if not in_dollar_quote and stripped.endswith(";"):
            stmt = "\n".join(current).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []

    # Catch any trailing statement without semicolon
    remaining = "\n".join(current).strip().rstrip(";").strip()
    if remaining:
        statements.append(remaining)

    return statements


async def run_migration():
    """Run the vector database migration."""
    database_url = get_database_url()
    
    print(f"📊 Connecting to database: {database_url.split('@')[1] if '@' in database_url else 'database'}")
    
    engine = create_async_engine(
        database_url,
        echo=True,
        future=True,
    )
    
    migration_file = Path(__file__).parent.parent / "supabase" / "migrations" / "20240101000000_enable_vector_extension.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    print(f"📄 Reading migration file: {migration_file.name}")
    
    with open(migration_file, "r") as f:
        migration_sql = f.read()
    
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session_maker() as session:
            print("🚀 Running migration...")
            
            # Split migration into individual statements, respecting $$ quoted blocks
            statements = split_sql_statements(migration_sql)
            
            for i, statement in enumerate(statements, 1):
                if statement:
                    try:
                        print(f"  Executing statement {i}/{len(statements)}...")
                        await session.execute(text(statement))
                        await session.commit()
                    except Exception as e:
                        # Some statements might fail if they already exist (like CREATE EXTENSION IF NOT EXISTS)
                        error_msg = str(e).lower()
                        if "already exists" in error_msg or "duplicate" in error_msg:
                            print(f"  ⚠️  Statement {i} skipped (already exists): {e}")
                            await session.rollback()
                        else:
                            print(f"  ❌ Error executing statement {i}: {e}")
                            await session.rollback()
                            raise
            
            print("✅ Migration completed successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)



