"""Adapters layer for finanzonline_uid.

Purpose
-------
Contains concrete implementations of application layer ports that
integrate with external systems (FinanzOnline SOAP services, email).

Contents
--------
* :mod:`.finanzonline` - FinanzOnline SOAP client adapters
* :mod:`.notification` - Email notification adapter
* :mod:`.output` - Output formatters for CLI

System Role
-----------
Outermost layer in clean architecture. Implements ports defined in
application layer. Contains I/O and external system integration.
"""

from __future__ import annotations
