# Open work

Standing backlog. Edit line by line, never rewrite wholesale. When an item is finished, delete
its line; the reason it closed belongs in the commit message, CHANGELOG or git history.

- [ ] (2026-10-02) [10] FOUND: `python -m finanzonline_uid` runs a separate lib_cli_exit_tools `cli_session` (`src/finanzonline_uid/__main__.py`, `_module_main`) instead of delegating to `cli.main()`; in btx_lib_mail the same shape made a usage error exit 1 under `python -m` and 2 from the console script, and bypassed main()'s handlers | size: one 3-line `__main__.py` plus its module-entry tests, own gate and release | open: found while fixing btx_lib_mail 2026-10-02 (moved here from its backlog 2026-10-05); the current bitranox_template_py_cli already delegates to main; not verified here that the exit codes actually diverge | next: run `python -m finanzonline_uid <cmd> --bad-flag` and the console script, compare exit codes, then port btx_lib_mail's `src/btx_lib_mail/__main__.py` and its module-entry tests
