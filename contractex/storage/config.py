"""
Database configuration with environment variable support.

Configuration priority:
1. Environment variables
2. Default values

For production, set environment variables:
    export POSTGRES_HOST=localhost
    export POSTGRES_PORT=5432
    export POSTGRES_USER=aahepburn
    export POSTGRES_DB=clause_docs
    export POSTGRES_PASSWORD=your_password
"""

from __future__ import annotations

import os
from typing import Any


def get_db_config() -> dict[str, Any]:
    """
    Get database configuration from environment variables or defaults.

    Returns:
        Dictionary with database connection parameters
    """
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "aahepburn"),
        "db_name": os.getenv("POSTGRES_DB", "clause_docs"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


# Backward compatibility - kept for existing imports
POSTGRES_CONFIG = get_db_config()


# Path configurations
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CUAD_DATA_DIR = os.path.join(DATA_DIR, "CUAD_v1")
CUAD_TXT_DIR = os.path.join(CUAD_DATA_DIR, "full_contract_txt")
CUAD_PDF_DIR = os.path.join(CUAD_DATA_DIR, "full_contract_pdf")


# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
