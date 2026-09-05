---
name: verify-deen-ops
description: >-
  Use this skill to run the required quality gates, unit test suite (79+ tests),
  and 60-module import verification before concluding any code changes in DEEN-OPS Terminal.
---

# DEEN-OPS Verification & Quality Gate

Run this verification workflow before concluding any refactor, feature addition, or bug fix.

## Quality Gate Criteria
- **Unit Tests**: All 79+ unit tests in `tests/` must pass with 0 failures.
- **Module Imports**: All 60 modules in `scripts/check_imports.py` must report `OK` with 0 failures.

## Verification Steps

### Step 1: Run Full Unit Test Suite

**Windows (PowerShell)**:
```powershell
$env:PYTHONPATH="."
.venv\Scripts\pytest.exe tests/ -v
```

**Linux / macOS (Bash)**:
```bash
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

### Step 2: Run Module Import Check

**Windows (PowerShell)**:
```powershell
.venv\Scripts\python.exe scripts/check_imports.py
```

**Linux / macOS (Bash)**:
```bash
.venv/bin/python scripts/check_imports.py
```

### Step 3: Evaluate Results
- If any test or import fails, inspect the traceback and resolve the issue before proceeding.
- Ensure no new files violate the strict layer separation rules defined in `AGENTS.md`.
