# Internomat Developer Guide

This file is the developer entry point. Detailed docs are split into focused files.

## Quick Links

- Setup and run from source: docs/development.md
- Build and release flow: docs/build_and_release.md
- Update client versioning policy: docs/update_client_versioning.md
- Current user-facing capabilities: docs/app_capabilities.md

## Tech Stack

- Language/runtime: Python (project currently maintained on 3.12)
- UI: PySide6
- Local data store: SQLite
- External data:
  - Leetify API (with Selenium fallback for rating/profile scraping)
  - MatchZy MySQL for match history sync
  - FTP demo download/parsing pipeline

## Most Used Commands

Run app from source:

```bash
python src/main.py
```

Run tests (excluding live tests):

```bash
pytest -m "not live"
```

Build installer (required version argument):

```bash
python src/build.py --installer --version 1.0.0
```

## Notes

- `src/build.py` requires `--version`.
- Builds run tests by default unless `--skip-tests` is supplied.
- `.env` is not bundled as plaintext into shipping artifacts.