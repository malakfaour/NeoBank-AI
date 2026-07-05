\# Contributing to NeoBank Lebanon



\## Branch Strategy

\- `main` → production only, final delivery

\- `develop` → integration branch, all PRs merge here

\- `feature/<name>` → your daily work branch



\## Daily Workflow

1\. `git checkout feature/<your-branch>`

2\. `git pull origin develop`

3\. Work, commit regularly

4\. `git push origin feature/<your-branch>`

5\. Open PR to `develop` when ticket is done



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

