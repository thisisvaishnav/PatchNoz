"""
Environment Loader

Loads variables from a `.env` file at the repo root (if present) into
os.environ, without overriding anything already set in the shell. Safe to
call from multiple modules - it's a no-op after the first successful call.

This exists because several modules (signoz_mcp_adapter, adapters/slack,
adapters/github) read configuration as module-level constants at import
time, so `.env` must be loaded before any of them are first imported.
"""

from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is an optional convenience
    load_dotenv = None

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_loaded = False


def load_env(dotenv_path: Optional[Path] = None) -> None:
    """Loads `.env` into os.environ exactly once. Existing env vars always win."""
    global _loaded
    if _loaded:
        return
    _loaded = True

    if load_dotenv is None:
        return

    path = dotenv_path or _ENV_PATH
    if path.exists():
        load_dotenv(dotenv_path=path, override=False)


load_env()
