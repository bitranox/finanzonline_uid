# Open work

Standing backlog. Edit line by line, never rewrite wholesale. When an item is finished, delete
its line; the reason it closed belongs in the commit message, CHANGELOG or git history.

- [ ] (2026-11-13) [15] USER: "/bitranox:coding-python-data-architecture" over src/finanzonline_uid - typed boundary models, enums, no internal dicts | size: ~90 findings in pass 1; foundation 18d6c5a plus 3 of 5 fixer sets done, cli.py not started | open: in flight, see handover.md | next: finish the fixer pass, re-analyse, make test, error-surface diff, CHANGELOG
- [ ] (2026-11-13) [40] FOUND: `check <UID> --format json` prints a configuration error as plain text on stderr with an empty stdout, so a caller parsing the JSON gets nothing (measured with every config source empty: exit 2 in both formats, stdout empty) | size: unknown - the error paths of check, config and config-deploy | open: first seen here, while reproducing the old [10]; not a regression, the exit code is right | next: decide whether --format json should emit a JSON error record on failure (and on which stream), then pin it in tests/test_cli_missing_credentials.py
