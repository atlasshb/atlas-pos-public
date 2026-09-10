# 03 — Backups that actually restore

> A backup that has never been restored is not a backup. It is a hope.

Everything below assumes the 3-2-1 shape: **3 copies, on 2 media/systems, 1
off-site**. The interesting part is not the tools — it is the failure modes.

## Design

- **Pick a source of truth and a target that isn't the same machine.** Backing a
  box up onto itself protects against almost nothing.
- **Per-tenant encryption.** Encrypt backups, and keep the repository password
  recoverable. Losing that password makes every copy unrecoverable.
- **Retention policy that actually runs.** Encryption + retention are separate
  features; a job can back up for months without ever pruning if retention
  silently fails.
- **Push, don't pull (or vice-versa, but know the blast radius).** If the backup
  host pulls from production using a key, rotating that key silently breaks
  backups — so backups must alarm on failure, not just log it.

## The failures that actually bit us

1. **A revoked key silently killed every backup.** The job still reported
   "completed". Rule: **the job must fail loudly and alert** when a source pull
   fails, and key rotations must include every consumer of the key.

2. **A stale lock disabled verification and retention for weeks.** The
   integrity check and the prune step stopped running; nobody noticed because
   the log only showed a status line. Rule: log **exit codes** as OK/FAIL, and
   alert on non-zero. Automate stale-lock clearing for the "no other job is
   running" case.

3. **`cmd | gzip > file` hides the exit code of `cmd`.** A database dump that
   failed at auth still produced a tiny, valid-looking gzip file every night.
   Rule: use `set -o pipefail`, and **assert a minimum size** — refuse to call a
   20-byte dump a success. Grep your fleet for this pattern.

4. **Dead sources padded the score.** A job that reports "16/18 OK" looks fine
   even when the two failures are *the client database that has never once been
   backed up*. Rule: remove dead sources so **any FAIL is a real FAIL**, and
   track *which* sources are in scope.

5. **Credentials in the backup job go stale.** A hardcoded DB password in a
   backup script quietly expires. Rule: read the live credential from the app
   config (or a secret store), not from a copy pasted months ago.

6. **The scheduled task only ran while a user was logged in.** Five nights, zero
   runs, no error. Rule: scheduled jobs must run headless (as a service/boot
   task), and you monitor **freshness of the last successful run**.

## The restore drill

Schedule it. Restore into a throwaway instance, assert row/table counts or a
known record, then tear it down. A passing restore drill is the only evidence
your backups work. Without it, you are guessing.

## Monitoring you want

- **Last-successful-run age** per source (not just "did the job exit 0").
- **Snapshot count and total size** trending (silent growth = leak; flatline =
  broken).
- **Integrity check result** and **retention applied** as explicit OK/FAIL.
- **Backup host disk free** — an off-site sync with no retention will one day
  fill the only disk it has.

## Takeaway

Treat backups as an untrusted, adversarial system: assume the quiet path is
broken, and prove it weekly with a real restore.
