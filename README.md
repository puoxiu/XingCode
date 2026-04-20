# XingCode

Step-by-step rebuild of a terminal coding agent inspired by MiniCode Python.

## Current Status

Phase 1 is implemented:

- `src/XingCode/core/types.py`
- `src/XingCode/core/tooling.py`
- `tests/unit/test_types.py`
- `tests/unit/test_tooling.py`

The rest of the system is intentionally not implemented yet.

## Quick Start

Use your named conda environment:

```bash
cd /Users/xing/Desktop/agent/cc/XingCode
conda create -n xingcode python=3.11 -y
conda activate xingcode
python -m pip install -r requirements.txt
python -m pip install -e . --no-build-isolation
python -m pytest -q
```

## Why There Is A `requirements.txt`

- `pyproject.toml` is the package definition.
- `requirements.txt` is here for quick environment setup, especially when using conda and then installing test dependencies into that environment.

At Phase 1, `requirements.txt` currently contains:

```text
pytest>=8.0.0
```
