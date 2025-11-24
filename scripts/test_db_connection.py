#!/usr/bin/env python
"""
Test script to verify database connection is using the correct Docker database
"""
import asyncio
import sys
import os
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from d4bl.database import init_db, async_session_maker, ResearchJob, get_database_url
from sqlalchemy import select, text


async def test_connection():
    """Test database connection and verify we're using the correct database"""
    print("=" * 60)
    print("Database Connection Test")
    print("=" * 60)
    
    # Show environment variables
    print("\n📋 Environment Variables:")
    print(f"  POSTGRES_HOST: {os.getenv('POSTGRES_HOST', 'NOT SET')}")
    print(f"  POSTGRES_DB: {os.getenv('POSTGRES_DB', 'NOT SET')}")
    print(f"  POSTGRES_USER: {os.getenv('POSTGRES_USER', 'NOT SET')}")
    print(f"  POSTGRES_PORT: {os.getenv('POSTGRES_PORT', 'NOT SET')}")
    
    # Show connection URL
    db_url = get_database_url()
    print(f"\n📊 Connection URL: {db_url}")
    
    # Verify host is 'postgres' (Docker service name), not 'localhost'
    if 'localhost' in db_url or '127.0.0.1' in db_url:
        print("\n⚠️  WARNING: Connection URL contains 'localhost' or '127.0.0.1'")
        print("   This means it might connect to a host Postgres instance!")
        print("   Expected: 'postgres' (Docker service name)")
        return False
    
    if 'postgres' not in db_url.split('@')[1].split('/')[0]:
        print("\n⚠️  WARNING: Connection URL doesn't use 'postgres' as hostname")
        print("   Expected: 'postgres' (Docker service name)")
        return False
    
    print("\n✅ Connection URL looks correct (using Docker service 'postgres')")
    
    # Test actual connection
    try:
        init_db()
        print("\n🔄 Testing database connection...")
        
        async with async_session_maker() as db:
            # Get current database name
            result = await db.execute(text("SELECT current_database(), current_user, inet_server_addr(), inet_server_port();"))
            row = result.fetchone()
            
            if row:
                db_name, db_user, server_addr, server_port = row
                print(f"\n✅ Connected successfully!")
                print(f"   Database: {db_name}")
                print(f"   User: {db_user}")
                print(f"   Server Address: {server_addr}")
                print(f"   Server Port: {server_port}")
                
                # Verify we're connected to the right database
                if db_name != 'd4bl_db':
                    print(f"\n⚠️  WARNING: Connected to database '{db_name}', expected 'd4bl_db'")
                    return False
                
                # Count jobs
                result = await db.execute(select(ResearchJob))
                jobs = result.scalars().all()
                print(f"\n📊 Found {len(jobs)} research jobs in database")
                
                print("\n✅ All checks passed! Connection is working correctly.")
                return True
            else:
                print("\n❌ Failed to get database information")
                return False
                
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)

