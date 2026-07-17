\# Contributing to NeoBank Lebanon



\## Branch Strategy

\- `main` → production only, final delivery

\- `develop` → integration branch, all PRs merge here

\- `feature/<name>` → your daily work branch



## Daily Workflow

1. `git fetch origin && git checkout -b feature/<name> origin/develop`

2. Work, commit regularly with real commit messages

3. Pull `develop` again before opening the PR

4. `git push origin feature/<name>`

5. Open PR to `develop` when ticket is done



\## Commit Message Format

TICKET-ID short description

Example: `DEVATTECH-32 JWT authentication implementation`



\## Pull Request Rules

\- Always merge into `develop`, never `main`

\- Minimum 1 teammate approval before merging

\- Never merge your own PR



\## Never

\- Push directly to `main` or `develop`

\- Commit `.env` files

\- Force push to shared branches

