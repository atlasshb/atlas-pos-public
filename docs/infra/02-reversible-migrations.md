# 02 — Reversible service migrations

Migrating a live service is where self-hosting gets scary. The pattern that
made it boring for us: **one service at a time, old one kept stopped (not
deleted), rollback is one command.**

## Preconditions

- A backup you have **actually restored** at least once (see `03`).
- A maintenance window the operator has agreed to.
- A health check that objectively says "this service works" (HTTP 200 on a
  meaningful route, a login, a query that returns data).
- The ability to put the old path back in seconds.

## The loop

1. **Inspect** — what does the service store, and where? Volumes, databases,
   cron/timers, environment, dependents.
2. **Snapshot** — copy the volume/data aside, dated. Verify it is non-empty and
   read it back before trusting it.
3. **Stand up the new instance** in parallel, on the new host/path, with the
   same data restored.
4. **Health-check the new instance** against the same objective check.
5. **Switch** the front door (proxy route / DNS) to the new instance.
6. **Health-check again** through the real ingress.
7. **Stop** — not delete — the old instance. Keep it for the rollback window.
8. **Verify with a real action** (a transaction, a login, a write-then-read).
9. After the window: decommission the old instance and remove the snapshot.

## Rollback

Because the old instance is stopped, not deleted, rollback is: switch the route
back, start the old container. That's it. Keep the rollback for longer than you
think you need — issues often appear days later under real load.

## Choosing what to migrate

Good candidates: a standalone app with its own data volume and no deep coupling.
Bad candidates: things that share a database, cache or agent with another
service unless you move the **stack**, not the single container.

## Gotchas we hit

- **Volume mounts are state.** A container that "just runs" may have an
  anonymous volume you forgot to copy.
- **Config drift.** The running config may not match the file in your repo.
  Read the live config before assuming.
- **Health checks that lie.** An app that returns 200 on `/` but errors on the
  real workflow is not healthy. Check the actual user action.
- **Scheduled tasks on the old host** keep firing after the move — disable the
  old timers/cron as part of the cutover.
- **Put the break-glass credential somewhere reachable before the outage**, not
  in the provider's web console you can't log into that day.

## Takeaway

Reversibility, not speed, is what makes migrations safe. If you can't roll back
in one command, you're not ready to switch.
