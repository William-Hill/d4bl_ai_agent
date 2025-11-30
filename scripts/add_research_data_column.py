#!/usr/bin/env python3
"""
Add research_data column to research_jobs table.

This script adds the research_data column to the existing research_jobs table
to store research data for use as reference in evaluations.

Usage:
    python scripts/add_research_data_column.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from d4bl.database import init_db


async def add_research_data_column():
    """Add research_data column to research_jobs table if it doesn't exist"""
    print("🔧 Adding research_data column to research_jobs table...")
    
    try:
        # Initialize database connection first
        init_db()
        
        # Import engine AFTER init_db() to ensure it's properly initialized
        from d4bl.database import engine
        
        # Verify engine is initialized
        if engine is None:
            print("❌ Error: Database engine is None. Check database connection settings.")
            return False
        
        async with engine.begin() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='research_jobs' AND column_name='research_data'
            """)
            result = await conn.execute(check_query)
            exists = result.scalar() is not None
            
            if exists:
                print("✅ research_data column already exists")
                return True
            
            # Add the column
            alter_query = text("""
                ALTER TABLE research_jobs 
                ADD COLUMN research_data JSON
            """)
            await conn.execute(alter_query)
            print("✅ Successfully added research_data column")
            return True
            
    except Exception as e:
        print(f"❌ Error adding research_data column: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(add_research_data_column())
    sys.exit(0 if success else 1)

