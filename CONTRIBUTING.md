# Contributing

This guide establishes a project skeleton and conventions to follow when adding files or features. Automated AI agents should follow these rules.

## File structure conventions
- Top-level main app: `Crypto2025.py`
- Chain scanners: `<CHAIN>/metrics_<chain>_whale_alert_realtime.py` (use scanner template)
- Services: `services/<domain>/` (e.g., `services/whale/whale_loader.py`)
- Tests: `tests/` using pytest
- Docs: `Development.md`, `Architecture.md`, `CHANGELOG_YYYY-MM-DD.md`
- Prompts: `.github/prompts/` (for AI agent tasks)

## Templates
- New scanners or services should be based on `templates/scanner_template.py` and `templates/service_template.py` to ensure safe import behavior and canonical event shapes.

## Environment & secrets
- Use `.env` (local, not committed) or CI secrets for `MONGO_URI`, `BLOCKBERRY_API_KEY`, `SUI_RPC_URL`, etc.
- Add a `.env.example` listing required env vars.

## Coding & PR checklist
- Run `python -m py_compile` on modified files
- Add or update tests for new loaders/scanners
- Ensure no import-time background threads spawn during test runs
- Document new files in `Development.md` and `Architecture.md` where appropriate
- Keep PRs small and focused

## How AI agents should create PRs
1. Create a branch `ai/<task>-<short>`
2. Use provided templates for new scanners/services
3. Run the local smoke checks and include outputs in PR description
4. Add CHANGELOG entry and update `Development.md` if new env vars are required
5. Open PR against `main` and request review

## Enforcement
- Reviewers should verify the template usage and absence of hard-coded secrets in diffs
