# Operations Runbook

## Database backups (Neon PostgreSQL)

**Provider:** Neon (managed Postgres) -- see `DATABASE_URL` / `DATABASE_URL_DIRECT` in `.env`.

**Plan:** Free (confirmed by Malak, repo/Neon-account owner, 2026-07-11)

**Automated backup mechanism:** Neon takes continuous storage snapshots
via its branching/history feature rather than traditional nightly dumps.
Every write is retained for a rolling window, and any point within that
window can be restored to a new branch without affecting the primary.

**Restore window:** 6 hours on the Free plan (capped at 1 GB of change
history, whichever limit is hit first -- per Neon's official docs,
neon.com/docs/introduction/plans, checked 2026-07-11). This is
substantially shorter than paid plans (1 day default, up to 30 days on
Scale) -- worth flagging to the team as a real operational risk: any
data-loss incident not caught within 6 hours cannot be point-in-time
recovered on the current plan.

**Recovery procedure (point-in-time restore):**
1. In the Neon console, open the project -> **Branches**.
2. Create a new branch from the primary, selecting a specific past
   timestamp (point-in-time restore) rather than "current".
3. This produces an isolated, fully-restored copy -- the primary
   database is never touched by this step.
4. Point a scratch `DATABASE_URL` at the new branch's connection string
   to verify data before deciding whether to promote/cut over.

## Restore drill (executed once, per DEVATTECH-123 acceptance criteria)

**Status:** DONE -- executed by Malak (Neon account owner) on 2026-07-14.

**Drill results:**
- Marker row: `users.id = 12`, `created_at = 2026-07-14 09:09:11 UTC`
- Restore point used: ~2026-07-14 09:00 UTC (12:00 PM Beirut) -- before the marker existed
- Branch created: new restore branch, parent = production, containing data/schema as of that timestamp
- Time to restore: near-instant (Neon branches are copy-on-write, not a
  traditional dump/restore)
- Verification: `select * from users where id = 12` on the restore
  branch returned 0 rows -- confirms the branch is genuinely restored
  to before the marker was created, not just a live clone of primary
- **Conclusion: point-in-time restore confirmed working correctly.**

## Related

- `/health/ready` (DEVATTECH-123) checks DB/Redis/Celery liveness for
  orchestrator readiness probes -- see `backend/app/main.py`.
- Env var drift between `app/core/config.py` and `.env.example` is
  caught automatically in CI by `backend/scripts/check_env_example.py`
  (DEVATTECH-121).