import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

# Ensure src is on the path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from d4bl.infra import database as db  # noqa: E402


async def add_trace_id_column():
    """Add trace_id column to research_jobs table if it does not exist."""
    print("🔧 Adding trace_id column to research_jobs table...")

    try:
        db.init_db()

        if db.engine is None:
            print("❌ Error: Database engine is None. Check database connection settings.")
            return False

        async with db.engine.begin() as conn:
            # Check if column already exists
            check_query = text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='research_jobs' AND column_name='trace_id';
                """
            )
            result = await conn.execute(check_query)
            exists = result.scalar() is not None

            if exists:
                print("✅ trace_id column already exists")
                return True

            # Add the column
            alter_query = text(
                """
                ALTER TABLE research_jobs
                ADD COLUMN trace_id VARCHAR(64);
                """
            )
            await conn.execute(alter_query)
            print("✅ Added trace_id column")

            # Create index for faster lookups
            index_query = text(
                """
                CREATE INDEX IF NOT EXISTS idx_research_jobs_trace_id
                ON research_jobs(trace_id);
                """
            )
            await conn.execute(index_query)
            print("✅ Created index on trace_id column")

            return True
    except Exception as e:
        print(f"❌ Error adding trace_id column: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(add_trace_id_column())
    sys.exit(0 if success else 1)




