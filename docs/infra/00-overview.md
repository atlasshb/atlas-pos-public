# Infrastructure notes — patterns from running a self-hosted stack

These are **engineering patterns and lessons**, not a map of any particular
deployment. The aim is to be useful to other small teams running their own
infrastructure, especially where a POS or client-facing service depends on it.

Nothing here describes a live system's topology, addresses, ports, accounts or
credentials. Client and operator data are excluded by design.

## Why these notes exist

Running your own stack is the price of data ownership. Most of the pain is not
in picking tools — it's in **migrations, backups, identity, silent failures and
incidents**. Those are what these notes cover.

## Contents

| Note | Topic |
|---|---|
| `01-right-sizing.md` | When you don't need Kubernetes (or a platform team) |
| `02-reversible-migrations.md` | Move one service at a time, with a one-command rollback |
| `03-backups-that-restore.md` | 3-2-1, the restore drill, and the silent failures that kill backups |
| `04-single-front-door-sso.md` | One reverse proxy, one identity provider, local fallbacks |
| `05-hardening-anti-mining.md` | Default-deny exposure and cryptominer defence |
| `06-silent-failure-operations.md` | Monitor job freshness, not just liveness |
| `07-llm-routing-and-agents.md` | Gateways, fallbacks, and agent/tool hygiene |
| `08-incident-lessons.md` | What we learned the hard way |

## The through-line

1. **Default to loopback** — a service that doesn't need public exposure should
   not be reachable from the internet.
2. **Make changes reversible** — snapshot, then change, then verify; rollback
   should be one command.
3. **A backup that was never restored is a hope** — test restores on a schedule.
4. **Silent failure is the enemy** — most outages were jobs that stopped running
   without anyone noticing.
5. **Least privilege everywhere** — no service account, no agent, no human gets
   more than the specific task needs.
