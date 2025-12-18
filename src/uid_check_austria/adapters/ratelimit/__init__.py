"""Rate limiting adapters for UID verification queries.

Provides rate limit tracking to monitor API call frequency and prevent
excessive usage of the FinanzOnline UID verification service.

Contents:
    * :class:`RateLimitTracker` - File-based rate limit tracker with sliding window
    * :class:`RateLimitStatus` - Current rate limit status information
"""

from __future__ import annotations

from .rate_limit_tracker import RateLimitStatus, RateLimitTracker

__all__ = ["RateLimitStatus", "RateLimitTracker"]
