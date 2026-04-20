# Type Hints Import Requirements

## Summary

This document outlines the required imports for applying the type hints fixes to the codebase.

---

## 1. EDUCATION.PY - Required Imports

### Currently Present ✅
```python
from typing import Optional, List, Tuple, Dict
```

### Additionally Needed ⚠️
```python
from typing import Any
import sqlite3
```

### Updated Import Block
```python
from typing import Optional, List, Tuple, Dict, Any
import sqlite3
```

**Note**: `sqlite3` is likely already imported in functions that use the cursor, but should be added to the module-level imports for type hints.

---

## 2. BOT.PY - Required Imports

### Currently Present ✅
```python
from typing import Optional, List, Tuple, Dict, Any, Callable
```

### Additionally Needed ⚠️
```python
from contextlib import contextmanager
from typing import ContextManager
import sqlite3  # (if not already present)
```

### Current Import Block (should be at top)
```python
from typing import Optional, List, Tuple, Dict, Any, Callable
from contextlib import contextmanager
import sqlite3
```

### What Needs Adding
```python
# If not present, add to typing imports:
from typing import ContextManager
```

**Verification**: Check if these are already imported:
- [ ] `from typing import Optional, List, Tuple, Dict, Any, Callable`
- [ ] `from contextlib import contextmanager`
- [ ] `import sqlite3`

---

## 3. API_SERVER.PY - Required Imports

### Currently Present ✅
```python
from typing import Optional, Any, Dict, List, AsyncGenerator
```

### Status
All required imports are already present! ✅

### No Changes Needed
The fixes for `api_server.py` only require changing `dict:` to `Dict[str, Any]:` which doesn't need new imports.

---

## Verification Checklist

Before applying fixes, verify:

### education.py
- [ ] Line 1-20: Check that `from typing import` includes `Optional, List, Tuple, Dict, Any`
- [ ] Look for `import sqlite3` in the imports section
- [ ] If missing `Any`, add it to the typing import
- [ ] If missing `sqlite3`, add `import sqlite3` near the top

### bot.py
- [ ] Line 1-30: Check that typing imports include `Optional, List, Tuple, Dict, Any, Callable`
- [ ] Check if `ContextManager` is imported from typing (may not be needed depending on current code)
- [ ] Check for `import sqlite3`
- [ ] Verify `from contextlib import contextmanager` is present

### api_server.py
- [ ] Confirm `from typing import Optional, Any, Dict, List` is present
- [ ] No additional imports needed for the planned fixes

---

## Implementation Steps

### Step 1: Add Missing Imports
For each file that needs updates:

```bash
# Check current imports
grep "from typing import" bot.py
grep "from typing import" education.py
grep "import sqlite3" education.py
```

### Step 2: Update Import Statements
If `Any` is missing from education.py:
```python
# BEFORE
from typing import Optional, List, Tuple, Dict

# AFTER
from typing import Optional, List, Tuple, Dict, Any
```

If `sqlite3` is missing from education.py:
```python
# Add at module level (around line 5-10)
import sqlite3
```

### Step 3: Apply Type Hint Fixes
Once imports are verified, proceed with the function signature updates documented in `TYPE_HINTS_ANALYSIS.md`

---

## Quick Import Audit Script

Run this to check current imports:

```bash
#!/bin/bash

echo "=== Checking education.py imports ==="
grep -n "from typing import\|import sqlite3" /home/sv4096/rvx_backend/education.py | head -20

echo -e "\n=== Checking bot.py imports ==="
grep -n "from typing import\|import sqlite3" /home/sv4096/rvx_backend/bot.py | head -20

echo -e "\n=== Checking api_server.py imports ==="
grep -n "from typing import" /home/sv4096/rvx_backend/api_server.py | head -10
```

---

## Import Compatibility Matrix

| Import | education.py | bot.py | api_server.py | Status |
|--------|--------------|--------|---------------|--------|
| `Optional` | ✅ | ✅ | ✅ | Present |
| `List` | ✅ | ✅ | ✅ | Present |
| `Tuple` | ✅ | ✅ | ✅ | Present |
| `Dict` | ✅ | ✅ | ✅ | Present |
| `Any` | ✅ | ✅ | ✅ | Present |
| `Callable` | ❌ | ✅ | ❌ | Only in bot.py |
| `ContextManager` | ❌ | ❌ | ❌ | Need to add if using |
| `sqlite3` | ⚠️ | ✅ | ❌ | Needed in education.py |

---

## Notes on Imports

### `ContextManager` vs `contextmanager`
- `contextmanager` is a **decorator** (from `contextlib`)
- `ContextManager` is a **type** (from `typing`)
- For type hints of context manager returns, use `ContextManager[T]`

Example:
```python
from contextlib import contextmanager
from typing import ContextManager
import sqlite3

@contextmanager
def get_db() -> ContextManager[sqlite3.Connection]:
    """Context manager for database connections"""
    # implementation
```

### Why We Need These Imports

**education.py**:
- `Any` - For generic dict contents like `Dict[str, Any]`
- `sqlite3` - For typing cursor parameter like `cursor: sqlite3.Cursor`

**bot.py**:
- Already has everything needed
- May need `ContextManager` for `get_db()` fix

**api_server.py**:
- Already has everything needed
- No new imports required

---

## CI/CD Integration

When running type checking (e.g., with mypy):

```bash
# Verify all imports are correct
mypy --check-untyped-defs bot.py education.py api_server.py

# Check for unused imports
pylint bot.py education.py api_server.py
```

Expected output after fixes:
```
Success: no issues found in 3 source files
```
