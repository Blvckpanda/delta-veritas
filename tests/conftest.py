"""Pytest configuration — make the ETL package importable without sys.path hacks."""

import sys
from pathlib import Path

ETL_DIR = Path(__file__).resolve().parent.parent / "src" / "etl"
if str(ETL_DIR) not in sys.path:
    sys.path.insert(0, str(ETL_DIR))
