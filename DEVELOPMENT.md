# Development Guide

## Python Dependency Management

This project uses Python 3.13.9 (or 3.10-3.13) with a virtual environment for dependency management.

### Quick Setup

1. **Create and activate virtual environment**:
   ```bash
   # Create venv (if it doesn't exist)
   python3.13 -m venv .venv
   
   # Activate it
   source .venv/bin/activate  # macOS/Linux
   # or
   .venv\Scripts\activate     # Windows
   ```

2. **Install dependencies**:
   ```bash
   # Option 1: Use the setup script (recommended)
   ./setup_env.sh
   
   # Option 2: Manual installation
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Dependency Files

- **`requirements.txt`**: Complete list of all Python dependencies with pinned versions
- **`pyproject.toml`**: Project metadata and core dependencies (used by CrewAI)

**Note**: The `requirements.txt` should match the versions in `pyproject.toml`. If they differ, `requirements.txt` takes precedence for `pip install`.

### Common Issues

#### Issue: `ModuleNotFoundError: No module named 'uvicorn'`

**Solution**: Activate the virtual environment first:
```bash
source .venv/bin/activate
python run_ui.py
```

#### Issue: `crewai` version conflicts

**Solution**: The project uses `crewai[tools]==1.5.0`. If you see version errors:
```bash
source .venv/bin/activate
pip install "crewai[tools]==1.5.0"
```

#### Issue: Python version mismatch

**Solution**: The project requires Python 3.10-3.13. If you have Python 3.14+:
```bash
# Install Python 3.13.9 using pyenv
pyenv install 3.13.9
pyenv local 3.13.9

# Recreate venv
rm -rf .venv
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the Application

#### Start API Server (Backend)

```bash
# Activate venv
source .venv/bin/activate

# Start server
python run_ui.py
```

The API will be available at `http://localhost:8000`

#### Start Next.js UI (Frontend)

```bash
cd ui-nextjs
npm install
npm run dev
```

The UI will be available at `http://localhost:3000`

### Updating Dependencies

1. **Update a specific package**:
   ```bash
   source .venv/bin/activate
   pip install --upgrade package-name
   pip freeze > requirements.txt  # Update requirements.txt
   ```

2. **Add a new package**:
   ```bash
   source .venv/bin/activate
   pip install new-package
   pip freeze > requirements.txt  # Update requirements.txt
   ```

### Virtual Environment Best Practices

- ✅ Always activate the venv before running Python scripts
- ✅ Commit `.venv/` to `.gitignore` (already done)
- ✅ Use `requirements.txt` for reproducible installs
- ✅ Keep `requirements.txt` and `pyproject.toml` in sync

### IDE Setup

#### VS Code

1. Open the project in VS Code
2. Select the Python interpreter: `Cmd+Shift+P` → "Python: Select Interpreter"
3. Choose `.venv/bin/python`

#### PyCharm

1. Open the project in PyCharm
2. Go to Settings → Project → Python Interpreter
3. Select "Add Interpreter" → "Existing environment"
4. Choose `.venv/bin/python`

