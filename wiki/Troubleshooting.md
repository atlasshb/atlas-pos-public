# Troubleshooting

Known failure modes from building and running this stack, and how to fix them.

## POS page returns 500 after installing the payment module

**Cause:** the module's asset glob doesn't match its folder name, so Odoo
resolves no assets and the POS config raises a `TypeError` on cache-url
generation. This is the classic Odoo module-rename trap.

**Fix:** the manifest `assets` path and the module folder name must match
exactly. Reinstall/upgrade (`-u <module>`) and restart Odoo to clear cached
manifests.

## Payment method not linked to a journal

**Cause:** the post-init hook references payment methods by xmlid, and the
module was renamed so the xmlid no longer resolves.

**Fix:** the seed pack resolves journals by **search**, not xmlid. If you
renamed the module, keep internal xmlid references consistent (or let the hook
search).

## Card terminal shows no reaction

Check, in order:
1. Terminal is online/paired at the PSP.
2. The `pos.payment.method` has the correct **terminal id** and **API key**.
3. The PSP account is active and the terminal is assigned.
4. Run a **test transaction** — some PSPs cache status for ~30s, and cancel
   may be limited to a few attempts.

## Backup job "succeeds" but the dump is tiny

**Cause:** `cmd | gzip > file` hides the exit code of `cmd` — a failed dump
still writes a small, valid gzip.

**Fix:** use `set -o pipefail` and assert a minimum file size; fail loudly if
below it. See `docs/infra/03-backups-that-restore.md`.

## A scheduled job silently stopped running

**Cause:** the job ran only while a user was logged in, or a stale lock blocked
it, or an empty config file stalled it.

**Fix:** run jobs headless (service/boot task); monitor **freshness of the last
successful run**, not just exit codes. See
`docs/infra/06-silent-failure-operations.md`.

## Site CSS broke after "cleaning" a cache

**Cause:** a generated cache was deleted by hand instead of via the app.

**Fix:** always use the application's own cache-clear mechanism. Never delete
generated artifacts manually.

## More

Repository docs: `docs/` (design) and `docs/infra/` (self-hosting patterns).
