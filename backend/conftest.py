"""Make backend/ importable from tests, matching how the app imports at runtime.

main.py does `from routers import ...` with backend/ as the working directory, so
tests use the same flat import root rather than a package prefix.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
