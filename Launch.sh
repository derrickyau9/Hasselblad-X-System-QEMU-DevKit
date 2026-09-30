#!/bin/sh
set -eu
cd "$(dirname "$0")"

if [ -x .venv-mac/bin/python ]; then
    PYTHON=.venv-mac/bin/python
else
    PYTHON_BIN="${PYTHON_BIN:-}"
    if [ -z "$PYTHON_BIN" ]; then
        PYTHON_BIN="$(command -v python3.13 2>/dev/null || command -v python3 2>/dev/null || true)"
    fi
    if [ -z "$PYTHON_BIN" ]; then
        echo "Python 3.11 or newer is required. Install python@3.13 with Homebrew." >&2
        exit 1
    fi
    "$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
    "$PYTHON_BIN" -m venv .venv-mac
    .venv-mac/bin/python -m pip install -e .
    PYTHON=.venv-mac/bin/python
fi

exec "$PYTHON" run_app.py "$@"
