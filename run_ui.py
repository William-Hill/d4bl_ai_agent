#!/usr/bin/env python
"""
Run the D4BL AI Agent UI server
"""
import uvicorn
import sys
import os
from pathlib import Path

# Add src to Python path
project_root = Path(__file__).parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    # Get port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"🚀 Starting D4BL AI Agent UI server...")
    print(f"📡 Server will be available at http://localhost:{port}")
    print(f"🌐 Access the UI at http://localhost:{port}/")
    print(f"📚 API docs at http://localhost:{port}/docs")
    print()
    
    uvicorn.run(
        "d4bl.api:app",
        host=host,
        port=port,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )

