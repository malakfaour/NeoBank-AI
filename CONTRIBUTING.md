# Contributing to NeoBank Lebanon

The authoritative guide for branching, commits, pull requests, code conventions, and everything else is:

**[docs/ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md)**

Read it before starting any task. All rules there take precedence over anything you may have seen elsewhere.

## Quick-start

1. `git fetch origin && git checkout -b feature/DEVATTECH-<id>-<short-name> origin/develop`
2. Work and commit with real messages: `fix(auth): correct OTP expiry check (DEVATTECH-99)`
3. Pull `develop` again before opening the PR
4. `git push origin feature/<name>`
5. Open PR to `develop` — never to `main`

For the full rules (migrations, async/sync DB, rate limiting, tests, and more), see [ENGINEERING_RULES.md](docs/ENGINEERING_RULES.md).