"""Domain-level behaviors supporting the minimal CLI transport.

Collect the placeholder behaviors that the CLI adapter exposes so that each
concern remains self-contained. Keeping these helpers together makes it easy to
swap in richer logging logic later without touching the transport surface.

Contents:
    * :func:`emit_greeting` – success-path helper that writes the canonical scaffold
      message.
    * :func:`raise_intentional_failure` – deterministic error hook used by tests and
      CLI flows to validate traceback handling.
    * :func:`noop_main` – placeholder entry used when callers expect a ``main``
      callable despite the domain layer being stubbed today.

System Role:
    Acts as the temporary domain surface for this template. Other modules import
    from here instead of duplicating literals so the public API stays coherent as
    features evolve.
"""

from __future__ import annotations

from typing import TextIO

import logging
import sys


CANONICAL_GREETING = "Hello World"

#: Module logger using standard logging interface.
logger = logging.getLogger(__name__)


def emit_greeting(*, stream: TextIO | None = None) -> None:
    r"""Write the canonical greeting to the provided text stream.

    Provide a deterministic success path that the documentation, smoke
    tests, and packaging checks can rely on while the real logging helpers
    are developed. Writes :data:`CANONICAL_GREETING` followed by a newline
    to the target stream.

    Args:
        stream: Optional text stream receiving the greeting. Defaults to
            :data:`sys.stdout` when ``None``.

    Side Effects:
        Writes to the target stream and flushes it when a ``flush`` attribute is
        available. Emits an INFO-level log message.

    Example:
        >>> from io import StringIO
        >>> buffer = StringIO()
        >>> emit_greeting(stream=buffer)
        >>> buffer.getvalue() == "Hello World\n"
        True
    """
    logger.info("Emitting canonical greeting", extra={"greeting": CANONICAL_GREETING})
    target = stream if stream is not None else sys.stdout
    target.write(f"{CANONICAL_GREETING}\n")
    if hasattr(target, "flush"):
        target.flush()


def raise_intentional_failure() -> None:
    """Raise ``RuntimeError`` so transports can exercise failure flows.

    CLI commands and tests need a guaranteed failure scenario to ensure the
    shared exit-code helpers and traceback toggles remain correct.
    Always raises ``RuntimeError`` with the message ``"I should fail"``.

    Raises:
        RuntimeError: Regardless of input.

    Side Effects:
        Emits an ERROR-level log message before raising the exception.

    Example:
        >>> raise_intentional_failure()
        Traceback (most recent call last):
        ...
        RuntimeError: I should fail
    """

    logger.error("About to raise intentional failure for testing", extra={"test_mode": True})
    raise RuntimeError("I should fail")


def noop_main() -> None:
    """Explicit placeholder callable for transports without domain logic yet.

    Some tools expect a module-level ``main`` even when the underlying
    feature set is still stubbed out. Exposing this helper makes that
    contract obvious and easy to replace later. Performs no work and
    returns immediately.

    Side Effects:
        Emits a DEBUG-level log message indicating the no-op execution.

    Example:
        >>> noop_main()
    """

    logger.debug("Executing noop_main placeholder")
    return None


__all__ = [
    "CANONICAL_GREETING",
    "emit_greeting",
    "raise_intentional_failure",
    "noop_main",
]
