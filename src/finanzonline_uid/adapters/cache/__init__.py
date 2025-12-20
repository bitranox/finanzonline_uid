"""Cache adapters for UID verification results.

Provides caching mechanisms to store and retrieve successful UID query
results, reducing redundant API calls to FinanzOnline.

Contents:
    * :class:`UidResultCache` - File-based cache with locking for concurrent access
"""

from __future__ import annotations

from .file_cache import UidResultCache

__all__ = ["UidResultCache"]
