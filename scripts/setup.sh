#!/usr/bin/env bash
set -euo pipefail

# Sophia — Project Setup Script
# Sets up the development environment from a fresh clone.

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Sophia Setup ==="
echo ""

# --- Check Python version ---
REQUIRED_MAJOR=3
REQUIRED_MINOR=11

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python ${REQUIRED_MAJOR}.${REQUIRED_MINOR}+ first."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt "$REQUIRED_MAJOR" ] || { [ "$PY_MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$PY_MINOR" -lt "$REQUIRED_MINOR" ]; }; then
    echo "ERROR: Python ${REQUIRED_MAJOR}.${REQUIRED_MINOR}+ required, found ${PY_VERSION}"
    exit 1
fi
echo "[ok] Python ${PY_VERSION}"

# --- Check / install uv ---
if ! command -v uv &>/dev/null; then
    echo "[..] uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "ERROR: uv installation failed. Install manually: https://docs.astral.sh/uv/"
        exit 1
    fi
fi
echo "[ok] uv $(uv --version 2>/dev/null | head -1)"

# --- Create .env if missing ---
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "[ok] Created .env from .env.example — edit it to add your API keys"
    else
        echo "[warn] No .env.example found, skipping .env creation"
    fi
else
    echo "[ok] .env already exists"
fi

# --- Install dependencies ---
echo "[..] Installing dependencies..."
uv sync --all-extras
echo "[ok] Dependencies installed"

# --- Verify hat structure ---
HATS_DIR="./hats"
if [ -d "$HATS_DIR" ]; then
    HAT_COUNT=$(find "$HATS_DIR" -name "hat.json" -maxdepth 2 | wc -l | tr -d ' ')
    echo "[ok] Found ${HAT_COUNT} hat(s) in ${HATS_DIR}/"
else
    echo "[warn] No hats/ directory found"
fi

# --- Run tests ---
echo "[..] Running tests..."
if uv run pytest --tb=short -q; then
    echo "[ok] All tests passed"
else
    echo "[warn] Some tests failed — check output above"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your ANTHROPIC_API_KEY (or set LLM_PROVIDER=ollama)"
echo "  2. Start the server:  uv run uvicorn sophia.main:app --reload"
echo "  3. Health check:      curl http://localhost:8000/health"
echo "  4. List tools:        curl http://localhost:8000/tools"
echo ""
