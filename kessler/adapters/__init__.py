"""Scanner adapters.

Each module here converts ONE scanner's native output into `Attempt` objects, and nothing else. See
`base.py` for the contract and `garak.py` for the reference implementation, including the format traps
that only appeared when a real report was parsed.
"""
from __future__ import annotations

# Importing an adapter module registers it. Keep this list explicit so a scanner cannot be silently
# absent from the registry: a missing adapter must fail at `available()`, not produce empty coverage.
from . import ai_infra_guard  # noqa: F401
from . import deepteam  # noqa: F401
from . import garak  # noqa: F401
from . import mcp_scanner  # noqa: F401
from . import pyrit  # noqa: F401
from .base import REGISTRY, AdapterError, AdapterSpec, available, get, read_jsonl, register  # noqa: F401

__all__ = [
    "REGISTRY", "AdapterError", "AdapterSpec", "available", "get", "read_jsonl", "register",
    "ai_infra_guard", "deepteam", "garak", "mcp_scanner", "pyrit",
]
