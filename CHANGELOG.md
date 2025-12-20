# Changelog

All notable changes to this project will be documented in this file following
the [Keep a Changelog](https://keepachangelog.com/) format.



## [2.0.0] - 2025-12-20

### Changed (BREAKING)

- **Package renamed** from `uid_check_austria` to `finanzonline_uid`
- **CLI commands renamed** from `uid-check-austria` / `uid_check_austria` to `finanzonline-uid` / `finanzonline_uid`
- **Environment variable prefix** changed from `UID_CHECK_AUSTRIA___` to `FINANZONLINE_UID___`
- **Configuration paths** changed from `uid-check-austria` to `finanzonline-uid`:
  - Linux: `~/.config/finanzonline-uid/`
  - macOS: `~/Library/Application Support/bitranox/FinanzOnline UID/`
- **Import statements** changed: `from uid_check_austria import ...` → `from finanzonline_uid import ...`

### Migration

To migrate from 1.x:
1. Update imports: replace `uid_check_austria` with `finanzonline_uid`
2. Update CLI calls: replace `uid-check-austria` with `finanzonline-uid`
3. Rename config directories if customized
4. Update environment variables: replace `UID_CHECK_AUSTRIA___` prefix with `FINANZONLINE_UID___`

## [1.0.0] - 2025-12-18

- initial release
