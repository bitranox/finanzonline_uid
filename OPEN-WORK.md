# Open work

Standing backlog. Edit line by line, never rewrite wholesale. When an item is finished, delete
its line; the reason it closed belongs in the commit message, CHANGELOG or git history.

- [ ] (2026-10-15) [10] FOUND: `check <UID> --no-email --format json` with NO credentials configured was seen to exit 0 after printing the configuration error (human format reportedly exits non-zero) | size: unknown - reproduce first | open: first seen 2026-10-15 by a refactor pass on HEAD and on the refactored code alike, UNVERIFIED: a re-run from the repo root exited 1 in both formats, but it picked up real credentials there, so it did not test the no-credentials case | next: reproduce with HOME, XDG_CONFIG_HOME and the working directory all pointing at an empty temp dir (no .env), compare the json and human exit codes, and do NOT run it where credentials load (it queries the live FinanzOnline service)
