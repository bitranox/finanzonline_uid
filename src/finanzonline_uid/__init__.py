"""Public package surface exposing metadata and configuration.

This module provides the public API for programmatic access to
UID verification functionality, package metadata, and configuration.
"""

from __future__ import annotations

from . import __init__conf__
from .__init__conf__ import print_info
from .config import get_config

# Standard package metadata (PEP 566)
__title__ = __init__conf__.title
__version__ = __init__conf__.version
__name__ = __init__conf__.name
__url__ = __init__conf__.homepage
__author__ = __init__conf__.author
__author_email__ = __init__conf__.author_email

__all__ = [
    "__author__",
    "__author_email__",
    "__title__",
    "__url__",
    "__version__",
    "get_config",
    "print_info",
]
