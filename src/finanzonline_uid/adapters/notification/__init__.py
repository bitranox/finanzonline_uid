"""Notification adapters.

Purpose
-------
Implement NotificationPort for sending UID verification result
notifications via email.

Contents
--------
* :class:`.email_adapter.EmailNotificationAdapter` - Email notifications

System Role
-----------
Adapters layer - integrates with btx_lib_mail for email delivery.
"""

from __future__ import annotations

from .email_adapter import EmailNotificationAdapter

__all__ = [
    "EmailNotificationAdapter",
]
