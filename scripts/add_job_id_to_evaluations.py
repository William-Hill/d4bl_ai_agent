"""
Migration script to add job_id column to evaluation_results table.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from d4bl import database as db


async def add_job_id_column():
    """Add job_id column to evaluation_results table if it doesn't exist"""
    print("🔧 Adding job_id column to evaluation_results table...")

    try:
        db.init_db()

        if db.engine is None:
            print("❌ Error: Database engine is None. Check database connection settings.")
            return False

        async with db.engine.begin() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='evaluation_results' AND column_name='job_id';
            """)
            result = await conn.execute(check_query)
            exists = result.scalar() is not None

            if exists:
                print("✅ job_id column already exists")
                return True

            # Add the column
            alter_query = text("""
                ALTER TABLE evaluation_results 
                ADD COLUMN job_id UUID REFERENCES research_jobs(job_id);
            """)
            await conn.execute(alter_query)
            print("✅ Added job_id column")

            # Create index for better query performance
            index_query = text("""
                CREATE INDEX IF NOT EXISTS idx_evaluation_results_job_id 
                ON evaluation_results(job_id);
            """)
            await conn.execute(index_query)
            print("✅ Created index on job_id column")

            return True

    except Exception as e:
        print(f"❌ Error adding job_id column: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(add_job_id_column())
    sys.exit(0 if success else 1)

