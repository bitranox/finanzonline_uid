"""Provide the ``python -m finanzonline_uid`` entry point.

Runs :func:`finanzonline_uid.cli.main`, the function the console scripts run,
so exit codes and traceback handling are identical however the CLI is started.
"""

from __future__ import annotations

from . import cli

if __name__ == "__main__":
    raise SystemExit(cli.main())
