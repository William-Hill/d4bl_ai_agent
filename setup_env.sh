#!/bin/bash
# Setup script for D4BL AI Agent environment

set -e

echo "🔧 Setting up D4BL AI Agent environment..."

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "📌 Detected Python version: $PYTHON_VERSION"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3.13 -m venv .venv || python3 -m venv .venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet

# Install essential packages first (for API server)
echo "📥 Installing essential packages (uvicorn, fastapi)..."
pip install uvicorn fastapi websockets python-dotenv --quiet

# Install all dependencies
echo "📥 Installing all dependencies from requirements.txt..."
echo "   (This may take a few minutes...)"

if pip install -r requirements.txt; then
    echo "✅ All dependencies installed successfully!"
else
    echo "⚠️  Some dependencies failed to install. Trying to install crewai separately..."
    pip install "crewai[tools]==1.5.0" || echo "⚠️  CrewAI installation had issues, but API server should still work"
fi

echo ""
echo "✨ Setup complete!"
echo ""
echo "To activate the environment, run:"
echo "  source .venv/bin/activate"
echo ""
echo "To start the API server, run:"
echo "  python run_ui.py"
echo ""

